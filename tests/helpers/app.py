import json
from asyncio import Event, create_task
from base64 import b64decode, b64encode
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Self, cast

import httpx
import itsdangerous
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from httpx import ASGITransport, AsyncClient, Response
from httpx_ws import AsyncWebSocketSession, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from mcp.shared._httpx_utils import McpHttpClientFactory
from starlette.requests import HTTPConnection
from wsproto.utilities import LocalProtocolError

from app.main import app
from app.models.accounts import User
from app.models.collaboration.workspace import SubscriptionPreference
from app.routers.dependencies import Authentication, get_authentication
from config import settings
from config.enums import ChannelEventResource, ChannelMessageType
from infra.db import clean_db
from infra.jobs import inline_jobs
from infra.messaging import Topic
from infra.oauth import Token

# http://testserver/ is the default base_url hardcoded in starlette
BASE_URL = "http://testserver"


class AppClient(AsyncClient):
    current_user: User | None = None

    def __init__(self, app: FastAPI, **kwargs):
        self.current_user = kwargs.pop("current_user", None)
        self._app = app
        app.dependency_overrides = {get_authentication: self._get_authentication}

        self._transport = ASGIWebSocketTransport(app=app)

        # Patch transport to avoid asyncio/mypy exit errors
        self._transport.__aexit__ = ASGITransport.__aexit__.__get__(self._transport)  # type: ignore
        super().__init__(transport=self._transport, **kwargs)

    @classmethod
    async def default_user(cls):
        user, is_new_login, _, _ = await User.get_or_create_by_oauth(Token.fake("dev@example.com"))
        if is_new_login:
            await SubscriptionPreference.ensure_defaults(user.id)
        return user

    async def _get_authentication(self, connection: HTTPConnection):
        authentication = Authentication(connection)
        if self.current_user:
            authentication.current_user = self.current_user
            await authentication.load()
        return authentication

    async def get_default_user(self):
        if not self.current_user:
            self.current_user, _, _ = await AppClient.default_user()
        return self.current_user

    @contextmanager
    def current_user_as(self, user: User):
        previous_user = self.current_user
        self.current_user = user
        try:
            yield
        finally:
            self.current_user = previous_user

    @contextmanager
    def logged_out(self):
        previous_user = self.current_user
        self.current_user = None
        try:
            yield
        finally:
            self.current_user = previous_user

    @property
    def session(self):
        session_cookie = self.cookies.get(settings.session_cookie_name)
        if not session_cookie:
            return {}
        unsigned = itsdangerous.TimestampSigner(settings.secret_key.get_secret_value()).unsign(session_cookie)
        return json.loads(b64decode(unsigned))

    def seed_session(self, **values) -> None:
        # Write the signed session cookie the way LazySessionMiddleware does — b64(json)
        # signed with the secret key — so the next request decodes these values. Auth comes
        # from a dependency override rather than the cookie, so a partial session is safe.
        payload = b64encode(json.dumps(values).encode())
        signer = itsdangerous.TimestampSigner(settings.secret_key.get_secret_value())
        self.cookies.set(settings.session_cookie_name, signer.sign(payload).decode())

    @asynccontextmanager
    async def connect_websocket(self, url: str) -> AsyncGenerator[AsyncWebSocketSession]:
        try:
            async with aconnect_ws(url, self) as websocket:  # type: ignore
                yield cast(AsyncWebSocketSession, websocket)
        except* LocalProtocolError:
            # Suppress send errors during WebSocket close — race between
            # in-flight broadcasts and the close handshake.
            pass

    @asynccontextmanager
    async def connect_channel(self, topic: Topic, params: dict | None = None) -> AsyncGenerator[AsyncWebSocketSession]:
        async with self.connect_websocket("/channels") as websocket:
            message: dict = {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": topic.stream,
                "topic_params": topic.params,
            }
            if params:
                message["params"] = params
            await websocket.send_json(message)
            confirmed = await websocket.receive_json()
            assert confirmed["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
            assert confirmed["topic_stream"] == topic.stream
            yield websocket


async def receive_event(websocket: AsyncWebSocketSession, resource: ChannelEventResource) -> dict:
    """Receive messages until we get an EVENT with the expected resource."""
    while True:
        response = await websocket.receive_json()
        if response.get("type") == ChannelMessageType.EVENT and response.get("resource") == resource:
            return response


@dataclass
class SSEEvent:
    event: str
    data: str

    @classmethod
    async def build_list_from_response(cls, response: Response) -> list[Self]:
        lines: list[str] = []
        async for line in response.aiter_lines():
            lines.append(line)

        results = []
        for i, line in enumerate(lines):
            if line.startswith("event:"):
                event = line.split(":")[1].strip()
                if i + 1 < len(lines):
                    data = lines[i + 1].split(":")[1].strip()
                    results.append(cls(event, data))

        return results


@pytest_asyncio.fixture(autouse=True)
async def setup_app_lifespan():
    should_stop = Event()
    is_started = Event()

    # Run the app lifespan in a separate task to ensure setup and teardown happen in the same event loop.
    async def lifespan_container(app: FastAPI):
        async with app.router.lifespan_context(app):
            await clean_db()
            is_started.set()
            await should_stop.wait()

    task = create_task(lifespan_container(app))
    await is_started.wait()
    yield app
    should_stop.set()
    await task


@pytest_asyncio.fixture()
async def client(setup_app_lifespan: FastAPI):
    default_user = await AppClient.default_user()
    async with AppClient(app=setup_app_lifespan, base_url=f"{BASE_URL}/", current_user=default_user) as client:
        client.follow_redirects = True
        yield client

    # Ensure all jobs are completed, or raise the first failure.
    # this is required because FastAPI doesn't wait for background tasks to complete before returning a response.
    inline_jobs.raise_first_failed()


@pytest.fixture(autouse=True, scope="function")
def custom_settings():
    with settings.override():
        yield


class McpClientFactory(McpHttpClientFactory):
    """Factory that creates httpx clients using ASGI transport for testing."""

    def __init__(self, app: FastAPI):
        self._app = app

    def __call__(
        self,
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
        **kwargs,
    ) -> AsyncClient:
        return AsyncClient(
            transport=ASGITransport(app=self._app),
            headers=headers,
            timeout=timeout,
            auth=auth,
            **kwargs,
        )


class McpClient:
    """MCP client for testing that uses ASGI transport."""

    def __init__(self, app: FastAPI, auth: str | None = None):
        self._app = app
        self.auth = auth
        self._client: Client | None = None

    async def __aenter__(self) -> Client:
        transport = StreamableHttpTransport(
            url=f"{BASE_URL}/mcp",
            auth=self.auth,
            httpx_client_factory=McpClientFactory(self._app),
        )
        self._client = Client(transport=transport)
        return await self._client.__aenter__()

    async def __aexit__(self, *args):
        if self._client:
            await self._client.__aexit__(*args)


@pytest_asyncio.fixture()
async def mcp_client(setup_app_lifespan: FastAPI):
    """MCP client fixture for testing MCP tools."""

    async def _create_client(user: User):
        return McpClient(app=setup_app_lifespan, auth=user.email)

    return _create_client
