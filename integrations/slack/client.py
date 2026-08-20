import time
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt

from app.models.accounts import User
from config import settings
from integrations.slack.models import SlackMessage
from integrations.slack.oauth import get_slack_oauth_token


def _is_rate_limited(exc: BaseException) -> bool:
    if not isinstance(exc, SlackApiError):
        return False
    return exc.response.get("error") == "ratelimited"


def _wait_for_retry_after(retry_state: RetryCallState) -> float:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, SlackApiError):
        retry_after = exc.response.headers.get("Retry-After")
        if retry_after:
            return float(retry_after)
    return min(2**retry_state.attempt_number, 60)


RETRY_DECORATOR = retry(
    retry=retry_if_exception(_is_rate_limited),
    stop=stop_after_attempt(5),
    wait=_wait_for_retry_after,
)

MAX_RESULTS_PER_PAGE = 100
MAX_PAGES = 100

# CookieAuthAsyncWebClient is not intended for production use. It is a local development
# implementation that uses xoxc/xoxd cookie-based authentication obtained from a logged-in
# browser session.
# Follow the instructions here to get the required tokens:
# https://github.com/korotovsky/slack-mcp-server/blob/master/docs/01-authentication-setup.md
# Then, save the `xoxc` and `xoxd` tokens as environment variables in your `.env.secrets` file. Like so:
# SLACK_XOXC_TOKEN="xoxc-..."
# SLACK_XOXD_TOKEN="xoxd-..."
#
# IMPORTANT NOTE: You will need to auth slack in the app as well, so your user has the integration and
# the logic to make ResearchSlackSearch works as it normally would.


class CookieAuthAsyncWebClient(AsyncWebClient):
    """
    AsyncWebClient subclass that uses xoxc/xoxd cookie-based authentication.
    This enables using personal Slack tokens in local development.

    NOT for production use. See:
    https://github.com/korotovsky/slack-mcp-server/blob/master/docs/01-authentication-setup.md
    """

    def __init__(self, xoxc_token: str, xoxd_token: str, **kwargs):
        super().__init__(token=xoxc_token, **kwargs)
        self.xoxd_token = xoxd_token

    def _build_cookies(self) -> dict[str, str]:
        return {
            "d": self.xoxd_token,
            "d-s": str(int(time.time()) - 10),
        }

    async def _request(
        self,
        *,
        http_verb: str,
        api_url: str,
        req_args: dict,
    ) -> dict:
        headers = req_args.get("headers", {})
        cookies = self._build_cookies()

        async with httpx.AsyncClient(timeout=30.0, cookies=cookies) as client:
            if http_verb == "GET":
                response = await client.get(api_url, headers=headers, params=req_args.get("params"))
            else:
                response = await client.post(
                    api_url,
                    headers=headers,
                    data=req_args.get("data"),
                    json=req_args.get("json"),
                )

            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "data": response.json() if response.content else {},
            }


class SlackClient:
    client: AsyncWebClient

    def __init__(
        self,
        access_token: str,
        xoxc_token: str | None = None,
        xoxd_token: str | None = None,
    ):
        if xoxc_token and xoxd_token:
            self.client = CookieAuthAsyncWebClient(xoxc_token=xoxc_token, xoxd_token=xoxd_token)
        else:
            self.client = AsyncWebClient(token=access_token)

    @classmethod
    async def create(cls, user: User) -> "SlackClient":
        xoxc = settings.slack_xoxc_token.get_secret_value() or None
        xoxd = settings.slack_xoxd_token.get_secret_value() or None

        if xoxc and xoxd:
            return cls(access_token="", xoxc_token=xoxc, xoxd_token=xoxd)

        oauth_token = await get_slack_oauth_token(user)
        if not oauth_token:
            raise Exception("User does not have a Slack OAuth token")

        return cls(access_token=oauth_token.access_token)

    async def get_user_identity(self) -> dict:
        try:
            response = await self.client.users_identity()
            if not isinstance(response.data, dict):
                raise Exception("Unexpected response format from Slack API")
            return response.data
        except SlackApiError as e:
            raise Exception(f"Slack API error: {e.response['error']}")

    async def get_user_info(self, user_id: str) -> dict:
        try:
            response = await self.client.users_info(user=user_id)
            if not isinstance(response.data, dict):
                raise Exception("Unexpected response format from Slack API")
            return response.data
        except SlackApiError as e:
            raise Exception(f"Slack API error: {e.response['error']}")

    async def get_team_info(self) -> dict:
        try:
            response = await self.client.team_info()
            if not isinstance(response.data, dict):
                raise Exception("Unexpected response format from Slack API")
            return response.data
        except SlackApiError as e:
            raise Exception(f"Slack API error: {e.response['error']}")

    async def search_messages(
        self,
        query: str,
        limit: int = MAX_RESULTS_PER_PAGE,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
    ) -> list[SlackMessage]:
        search_query = self._build_search_query(query, starts_at, ends_at)
        results: list[SlackMessage] = []
        page = 1
        per_page = min(limit, MAX_RESULTS_PER_PAGE)

        while len(results) < limit and page <= MAX_PAGES:
            try:
                response = await self.client.search_messages(
                    query=search_query,
                    count=per_page,
                    page=page,
                    sort="timestamp",
                    sort_dir="desc",
                )
            except SlackApiError:
                break

            messages_data: dict[str, Any] = response.get("messages", {})
            matches: list[dict] = messages_data.get("matches", [])

            for match in matches:
                if len(results) >= limit:
                    break
                results.append(self._parse_message(match))

            pagination: dict = messages_data.get("pagination", {})
            if page >= pagination.get("page_count", 1):
                break

            page += 1

        return results

    def _build_search_query(self, query: str, starts_at: datetime | None, ends_at: datetime | None) -> str:
        parts = [query]
        if starts_at:
            parts.append(f"after:{starts_at.strftime('%Y-%m-%d')}")
        if ends_at:
            parts.append(f"before:{ends_at.strftime('%Y-%m-%d')}")
        return " ".join(parts)

    def _parse_message(self, match: dict) -> SlackMessage:
        channel: dict = match.get("channel", {})
        permalink = match.get("permalink", "")
        thread_ts = match.get("thread_ts") or self._extract_thread_ts_from_permalink(permalink)
        return SlackMessage(
            message_id=match.get("iid", ""),
            channel_id=channel.get("id", ""),
            channel_name=channel.get("name", ""),
            text=match.get("text", ""),
            timestamp=match.get("ts", ""),
            username=match.get("username", ""),
            permalink=permalink,
            team_id=match.get("team", ""),
            thread_ts=thread_ts,
        )

    def _extract_thread_ts_from_permalink(self, permalink: str) -> str | None:
        if not permalink:
            return None
        parsed = urlparse(permalink)
        params = parse_qs(parsed.query)
        thread_ts_list = params.get("thread_ts")
        return thread_ts_list[0] if thread_ts_list else None

    @RETRY_DECORATOR
    async def get_conversation_history(
        self,
        channel_id: str,
        oldest: str | None = None,
        latest: str | None = None,
        limit: int = 50,
    ) -> list[SlackMessage]:
        try:
            response = await self.client.conversations_history(
                channel=channel_id,
                oldest=oldest,
                latest=latest,
                limit=limit,
                inclusive=True,
            )
        except SlackApiError:
            return []

        messages: list[dict] = response.get("messages", [])
        return [self._parse_history_message(msg, channel_id) for msg in messages]

    @RETRY_DECORATOR
    async def get_thread_replies(
        self,
        channel_id: str,
        thread_ts: str,
        limit: int = 20,
        include_parent: bool = False,
    ) -> list[SlackMessage]:
        try:
            response = await self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=limit + 1,
            )
        except SlackApiError:
            return []

        messages: list[dict] = response.get("messages", [])
        if include_parent:
            return [self._parse_history_message(msg, channel_id) for msg in messages[:limit]]
        replies = messages[1:] if len(messages) > 1 else []
        return [self._parse_history_message(msg, channel_id) for msg in replies[-limit:]]

    def _parse_history_message(self, message: dict, channel_id: str) -> SlackMessage:
        return SlackMessage(
            message_id=message.get("ts", ""),
            channel_id=channel_id,
            channel_name="",
            text=message.get("text", ""),
            timestamp=message.get("ts", ""),
            username=message.get("user", ""),
            permalink="",
            team_id=message.get("team", ""),
            thread_ts=message.get("thread_ts"),
        )
