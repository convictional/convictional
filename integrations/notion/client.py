import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

import httpx
from notion_client import AsyncClient
from notion_client.errors import APIErrorCode, APIResponseError, HTTPResponseError, RequestTimeoutError

# Pinned per-deploy. Notion only bumps on breaking changes; pinning prevents silent
# regressions.
NOTION_API_VERSION = "2026-03-11"
NOTION_BASE_URL = "https://api.notion.com/v1"

T = TypeVar("T")

# 3 RPS average per integration token. We bucket conservatively.
DEFAULT_RATE_LIMIT_RPS = 3.0
DEFAULT_RATE_LIMIT_BURST = 3

# Retry caps for transient errors. 429/529 honor Retry-After; 5xx use exponential backoff.
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_CAP_SECONDS = 30.0

# Notion does not publish a numeric burst ceiling. Default request timeout is
# generous because some block-children fetches can be slow.
DEFAULT_TIMEOUT = httpx.Timeout(10.0, read=30.0, write=10.0, connect=10.0)


class NotionAPIError(Exception):
    def __init__(self, status_code: int, code: str | None, message: str, request_id: str | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id
        super().__init__(f"Notion API error {status_code} ({code}): {message}")


class NotionAuthError(NotionAPIError):
    """Raised for 401 / invalid_token style errors. The caller should mark the connection as invalid."""


@dataclass
class NotionWorkspaceInfo:
    bot_id: str
    workspace_id: str | None
    workspace_name: str | None


@dataclass
class NotionPageListItem:
    notion_page_id: str
    title: str
    parent_id: str | None
    last_edited_time: datetime | None
    url: str | None


@dataclass
class NotionPageListPage:
    items: list[NotionPageListItem]
    next_cursor: str | None
    has_more: bool


@dataclass
class NotionPageMetadata:
    notion_page_id: str
    title: str
    parent_id: str | None
    last_edited_time: datetime | None
    url: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotionBlockChildrenPage:
    blocks: list[dict[str, Any]]
    next_cursor: str | None
    has_more: bool


@dataclass
class NotionNode:
    node_id: str
    kind: str
    title: str
    parent_id: str | None
    parent_kind: str | None
    last_edited_time: datetime | None
    url: str | None
    has_children: bool


@dataclass
class NotionNodeListPage:
    nodes: list[NotionNode]
    next_cursor: str | None
    has_more: bool


@dataclass
class NotionChildNode:
    node_id: str
    kind: str
    title: str
    has_children: bool


@dataclass
class NotionChildNodeListPage:
    nodes: list[NotionChildNode]
    next_cursor: str | None
    has_more: bool


@dataclass
class NotionDataSourceRef:
    data_source_id: str
    name: str | None


@dataclass
class NotionDatabaseInfo:
    database_id: str
    title: str
    data_sources: list[NotionDataSourceRef]


@dataclass
class NotionDataSourceQueryPage:
    rows: list[dict[str, Any]]
    next_cursor: str | None
    has_more: bool


class _TokenBucket:
    """Simple async token bucket. Tokens refill at `rate` per second up to `burst`."""

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last_refill
                if elapsed > 0:
                    self._tokens = min(float(self._burst), self._tokens + elapsed * self._rate)
                    self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                await asyncio.sleep(deficit / self._rate)


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Notion returns trailing 'Z'; fromisoformat in 3.13 accepts it but normalize to be safe.
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _extract_title(properties: dict[str, Any] | None) -> str:
    if not properties:
        return ""
    for prop in properties.values():
        if not isinstance(prop, dict) or prop.get("type") != "title":
            continue
        rich_text = prop.get("title") or []
        return "".join(item.get("plain_text", "") for item in rich_text if isinstance(item, dict))
    return ""


def _extract_rich_text_title(title: list[dict[str, Any]] | None) -> str:
    if not title or not isinstance(title, list):
        return ""
    return "".join(item.get("plain_text", "") for item in title if isinstance(item, dict))


def _normalize_database_id(parent: dict[str, Any]) -> str | None:
    """Normalize a data_source parent up to its owning database id.

    A data_source_id parent reports the data-source id under `parent["data_source_id"]`,
    but the tree must key on the database id, which lives in the *sibling*
    `parent["database_id"]` key. This is the single shared helper so the same
    database never appears under two ids.
    """
    database_id = parent.get("database_id")
    return database_id if isinstance(database_id, str) else None


def _extract_parent(parent: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Return (parent_id, parent_kind) from a Notion `parent` object.

    `block_id` parents are returned as-is here (id, "block"); callers that need a
    tree node resolve them lazily via `resolve_containing_page`.
    """
    if not parent or not isinstance(parent, dict):
        return None, None
    parent_type = parent.get("type")
    if parent_type == "page_id":
        value = parent.get("page_id")
        return (value if isinstance(value, str) else None), "page"
    if parent_type == "database_id":
        value = parent.get("database_id")
        return (value if isinstance(value, str) else None), "database"
    if parent_type == "data_source_id":
        return _normalize_database_id(parent), "database"
    if parent_type == "workspace":
        return None, "workspace"
    if parent_type == "block_id":
        value = parent.get("block_id")
        return (value if isinstance(value, str) else None), "block"
    if parent_type == "agent_id":
        return None, None
    return None, None


class NotionClient:
    def __init__(
        self,
        access_token: str,
        *,
        rate_limit_rps: float = DEFAULT_RATE_LIMIT_RPS,
        rate_limit_burst: int = DEFAULT_RATE_LIMIT_BURST,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._access_token = access_token
        self._timeout = timeout
        self._transport = transport
        self._bucket = _TokenBucket(rate=rate_limit_rps, burst=rate_limit_burst)

        # The SDK collapses httpx's granular timeout into a single scalar (timeout_ms),
        # so derive it from our most generous leg (the read timeout) to keep slow
        # block-children fetches alive. retry=False because we keep our own backoff below.
        timeout_ms = int((timeout.read or 30.0) * 1000)
        injected = httpx.AsyncClient(transport=transport) if transport is not None else None
        self._sdk = AsyncClient(
            auth=access_token,
            notion_version=NOTION_API_VERSION,
            base_url=NOTION_BASE_URL.removesuffix("/v1"),
            timeout_ms=timeout_ms,
            retry=False,
            client=injected,
        )

    async def aclose(self) -> None:
        await self._sdk.aclose()

    async def __aenter__(self) -> "NotionClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _call(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Choke point for every SDK call: rate-limit, then map/retry errors using our policy."""
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            await self._bucket.acquire()
            try:
                return await operation()
            except APIResponseError as exc:
                # exc.code is an APIErrorCode (str-enum); use .value so the stored/compared
                # code is the wire string ("unauthorized") not "APIErrorCode.Unauthorized".
                code: str | None = exc.code.value if exc.code is not None else None
                if exc.status == 401 or code == "unauthorized":
                    raise NotionAuthError(exc.status, code, str(exc), exc.request_id) from exc

                if self._is_retryable(exc.status, code) and attempt < MAX_RETRIES - 1:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    await self._sleep_for_retry(retry_after, attempt)
                    last_error = exc
                    continue

                raise NotionAPIError(exc.status, code, str(exc), exc.request_id) from exc
            except HTTPResponseError as exc:
                # Non-API HTTP error (e.g. an unrecognized error code). request_id is still exposed.
                code = exc.code.value if isinstance(exc.code, APIErrorCode) else (exc.code or None)
                if self._is_retryable(exc.status, code) and attempt < MAX_RETRIES - 1:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    await self._sleep_for_retry(retry_after, attempt)
                    last_error = exc
                    continue
                raise NotionAPIError(exc.status, code, str(exc), exc.request_id) from exc
            except RequestTimeoutError as exc:
                # Transport/timeout failure with no HTTP response, so no request_id is available.
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    await self._sleep_backoff(attempt)
                    continue
                raise NotionAPIError(0, "timeout", str(exc), None) from exc

        if last_error is not None:
            raise NotionAPIError(0, "exhausted", str(last_error)) from last_error
        raise NotionAPIError(0, "exhausted", "Notion request exhausted retries")

    @staticmethod
    def _is_retryable(status_code: int, code: str | None) -> bool:
        if status_code in (429, 529, 500, 502, 503, 504):
            return True
        return code in {"rate_limited", "conflict_error", "internal_server_error", "service_unavailable"}

    @staticmethod
    async def _sleep_for_retry(retry_after: str | None, attempt: int) -> None:
        if retry_after is not None:
            try:
                await asyncio.sleep(float(retry_after))
                return
            except ValueError:
                pass
        await NotionClient._sleep_backoff(attempt)

    @staticmethod
    async def _sleep_backoff(attempt: int) -> None:
        delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2**attempt))
        await asyncio.sleep(delay)

    async def validate_token(self) -> NotionWorkspaceInfo:
        body = await self._call(lambda: self._sdk.users.me())
        bot = body.get("bot") or {}
        workspace_info = bot.get("workspace_name")
        owner = bot.get("owner") or {}
        workspace_id = owner.get("workspace_id") if isinstance(owner, dict) else None
        return NotionWorkspaceInfo(
            bot_id=body.get("id", ""),
            workspace_id=workspace_id if isinstance(workspace_id, str) else None,
            workspace_name=workspace_info if isinstance(workspace_info, str) else None,
        )

    async def list_accessible_pages(self, cursor: str | None = None) -> NotionPageListPage:
        body = await self._call(
            lambda: self._sdk.search(
                filter={"property": "object", "value": "page"},
                sort={"timestamp": "last_edited_time", "direction": "descending"},
                page_size=100,
                start_cursor=cursor,
            )
        )
        items: list[NotionPageListItem] = []
        for result in body.get("results", []):
            if result.get("object") != "page":
                continue
            parent_id, _ = _extract_parent(result.get("parent"))
            items.append(
                NotionPageListItem(
                    notion_page_id=result.get("id", ""),
                    title=_extract_title(result.get("properties")),
                    parent_id=parent_id,
                    last_edited_time=_parse_iso8601(result.get("last_edited_time")),
                    url=result.get("url"),
                )
            )
        return NotionPageListPage(
            items=items,
            next_cursor=body.get("next_cursor"),
            has_more=bool(body.get("has_more")),
        )

    async def list_accessible_nodes(self, cursor: str | None = None) -> NotionNodeListPage:
        # Search is run UNFILTERED so both pages and data_sources surface: the search
        # filter only accepts object values "page" or "data_source" (not "database"),
        # and an unfiltered search avoids that ambiguity while still returning the
        # "page"/"data_source" objects the kind branching below expects.
        body = await self._call(
            lambda: self._sdk.search(
                sort={"timestamp": "last_edited_time", "direction": "descending"},
                page_size=100,
                start_cursor=cursor,
            )
        )
        nodes: list[NotionNode] = []
        for result in body.get("results", []):
            node = self._node_from_search_result(result)
            if node is not None:
                nodes.append(node)
        return NotionNodeListPage(
            nodes=nodes,
            next_cursor=body.get("next_cursor"),
            has_more=bool(body.get("has_more")),
        )

    @staticmethod
    def _node_from_search_result(result: dict[str, Any]) -> NotionNode | None:
        if not isinstance(result, dict):
            return None
        object_type = result.get("object")
        parent_id, parent_kind = _extract_parent(result.get("parent"))
        last_edited_time = _parse_iso8601(result.get("last_edited_time"))
        url = result.get("url")
        if object_type == "page":
            # Search results don't carry a has_children flag for pages, so we can't
            # know cheaply whether a page has sub-pages/databases. Treat every page as
            # expandable: the chevron is always shown and expansion lazily fetches
            # children (revealing "No pages inside" for a genuine leaf). The alternative
            # — a block-children probe per page — would cost N rate-limited calls on the
            # list endpoint. Nested pages from list_child_nodes still get an accurate
            # has_children from the block payload.
            return NotionNode(
                node_id=result.get("id", ""),
                kind="page",
                title=_extract_title(result.get("properties")),
                parent_id=parent_id,
                parent_kind=parent_kind,
                last_edited_time=last_edited_time,
                url=url,
                has_children=True,
            )
        if object_type == "data_source":
            # Normalize a data source up to its owning database so the same database
            # never appears under two ids. The database id lives on the data source's
            # `database_parent.database_id` (its parent reference).
            database_id = _normalize_database_id(result.get("parent") or {})
            if not isinstance(database_id, str):
                database_id = result.get("database_id")
            return NotionNode(
                node_id=database_id if isinstance(database_id, str) else result.get("id", ""),
                kind="database",
                title=_extract_rich_text_title(result.get("title")),
                parent_id=parent_id,
                parent_kind=parent_kind,
                last_edited_time=last_edited_time,
                url=url,
                has_children=True,
            )
        return None

    async def list_child_nodes(self, parent_id: str, cursor: str | None = None) -> NotionChildNodeListPage:
        page = await self.get_block_children(parent_id, cursor=cursor)
        nodes: list[NotionChildNode] = []
        for block in page.blocks:
            block_type = block.get("type")
            if block_type not in ("child_page", "child_database"):
                continue
            payload = block.get(block_type) or {}
            nodes.append(
                NotionChildNode(
                    node_id=block.get("id", ""),
                    kind="page" if block_type == "child_page" else "database",
                    title=payload.get("title", "") if isinstance(payload, dict) else "",
                    has_children=True if block_type == "child_database" else bool(block.get("has_children")),
                )
            )
        return NotionChildNodeListPage(
            nodes=nodes,
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )

    async def get_database(self, database_id: str) -> NotionDatabaseInfo:
        body = await self._call(lambda: self._sdk.databases.retrieve(database_id=database_id))
        data_sources: list[NotionDataSourceRef] = []
        for source in body.get("data_sources") or []:
            if not isinstance(source, dict):
                continue
            source_id = source.get("id")
            if not isinstance(source_id, str):
                continue
            data_sources.append(NotionDataSourceRef(data_source_id=source_id, name=source.get("name")))
        return NotionDatabaseInfo(
            database_id=body.get("id", database_id),
            title=_extract_rich_text_title(body.get("title")),
            data_sources=data_sources,
        )

    async def query_data_source(self, data_source_id: str, cursor: str | None = None) -> NotionDataSourceQueryPage:
        body = await self._call(
            lambda: self._sdk.data_sources.query(
                data_source_id=data_source_id,
                start_cursor=cursor,
                page_size=100,
            )
        )
        return NotionDataSourceQueryPage(
            rows=list(body.get("results", [])),
            next_cursor=body.get("next_cursor"),
            has_more=bool(body.get("has_more")),
        )

    async def resolve_containing_page(self, block_id: str) -> str | None:
        """Walk a block_id parent chain up to the owning page/database id.

        A page nested inside a column/toggle/synced-block reports a `block_id` parent
        that is not itself a tree node. We loop `blocks.retrieve` up the chain until the
        parent type is no longer `block_id`, returning the owning page or database id.
        Resolved lazily — only call this for an edge that actually matters.
        """
        seen: set[str] = set()
        current_id: str | None = block_id
        while isinstance(current_id, str) and current_id not in seen:
            seen.add(current_id)
            retrieve_id = current_id
            body = await self._call(lambda: self._sdk.blocks.retrieve(block_id=retrieve_id))
            parent_id, parent_kind = _extract_parent(body.get("parent"))
            if parent_kind != "block":
                return parent_id
            current_id = parent_id
        return None

    async def get_page(self, page_id: str) -> NotionPageMetadata:
        body = await self._call(lambda: self._sdk.pages.retrieve(page_id=page_id))
        parent_id, _ = _extract_parent(body.get("parent"))
        return NotionPageMetadata(
            notion_page_id=body.get("id", page_id),
            title=_extract_title(body.get("properties")),
            parent_id=parent_id,
            last_edited_time=_parse_iso8601(body.get("last_edited_time")),
            url=body.get("url"),
            raw=body,
        )

    async def get_block_children(self, block_id: str, cursor: str | None = None) -> NotionBlockChildrenPage:
        body = await self._call(
            lambda: self._sdk.blocks.children.list(block_id=block_id, start_cursor=cursor, page_size=100)
        )
        return NotionBlockChildrenPage(
            blocks=list(body.get("results", [])),
            next_cursor=body.get("next_cursor"),
            has_more=bool(body.get("has_more")),
        )

    async def walk_page_blocks(self, page_id: str) -> AsyncIterator[dict[str, Any]]:
        # Synced-block dedup: track originals we've already walked in this page.
        # Duplicates point at the original via synced_from.block_id; we emit the
        # duplicate's shell once with a `_synced_duplicate` flag so the converter
        # can skip rendering, then we do NOT re-walk the original's children.
        seen_synced_originals: set[str] = set()

        async for block in self._walk(page_id, depth=0, seen_synced_originals=seen_synced_originals):
            yield block

    async def _iter_children(self, block_id: str | None) -> AsyncIterator[dict[str, Any]]:
        if not isinstance(block_id, str):
            return
        cursor: str | None = None
        while True:
            page = await self.get_block_children(block_id, cursor=cursor)
            for block in page.blocks:
                yield block
            if not page.has_more:
                return
            cursor = page.next_cursor

    async def _walk(
        self,
        block_id: str,
        *,
        depth: int,
        seen_synced_originals: set[str],
    ) -> AsyncIterator[dict[str, Any]]:
        cursor: str | None = None
        while True:
            page = await self.get_block_children(block_id, cursor=cursor)
            for block in page.blocks:
                block_type = block.get("type")
                augmented = {**block, "_depth": depth}

                if block_type == "synced_block":
                    synced = block.get("synced_block") or {}
                    synced_from = synced.get("synced_from")
                    if synced_from and isinstance(synced_from, dict):
                        original_id = synced_from.get("block_id")
                        augmented["_synced_duplicate"] = True
                        yield augmented
                        if isinstance(original_id, str) and original_id not in seen_synced_originals:
                            seen_synced_originals.add(original_id)
                            async for child in self._walk(
                                original_id,
                                depth=depth + 1,
                                seen_synced_originals=seen_synced_originals,
                            ):
                                yield child
                        continue

                    # Original synced block — record its id so any future duplicate dedupes.
                    block_self_id = block.get("id")
                    if isinstance(block_self_id, str):
                        seen_synced_originals.add(block_self_id)
                    yield augmented
                    if block.get("has_children") and isinstance(block_self_id, str):
                        async for child in self._walk(
                            block_self_id,
                            depth=depth + 1,
                            seen_synced_originals=seen_synced_originals,
                        ):
                            yield child
                    continue

                if block_type == "table":
                    # GFM tables must render as one contiguous unit, so we gather the
                    # table_row children here and hand the renderer a self-contained
                    # block rather than yielding the rows separately (they'd be skipped
                    # and vanish). We stash the `table_row` payloads (each {"cells": …})
                    # since that's all the renderer needs — the row block envelope is noise.
                    augmented["_table_rows"] = [
                        row.get("table_row") or {}
                        async for row in self._iter_children(block.get("id"))
                        if row.get("type") == "table_row"
                    ]
                    yield augmented
                    continue

                yield augmented

                # child_page / child_database are tree boundaries — do NOT recurse.
                if block_type in ("child_page", "child_database"):
                    continue

                if block.get("has_children"):
                    block_self_id = block.get("id")
                    if isinstance(block_self_id, str):
                        async for child in self._walk(
                            block_self_id,
                            depth=depth + 1,
                            seen_synced_originals=seen_synced_originals,
                        ):
                            yield child

            if not page.has_more:
                return
            cursor = page.next_cursor
