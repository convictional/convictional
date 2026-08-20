import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from integrations.notion.blocks_to_text import blocks_to_text
from integrations.notion.client import (
    NOTION_API_VERSION,
    NotionAPIError,
    NotionAuthError,
    NotionClient,
    _extract_parent,
)

# The notion-sdk-py client identifies itself with this User-Agent on every request.
SDK_USER_AGENT = "ramnes/notion-sdk-py@3.1.0"


def _client_with_handler(handler: Callable[[httpx.Request], httpx.Response]) -> NotionClient:
    transport = httpx.MockTransport(handler)
    # Use a wide-open rate limit in tests so the bucket isn't a source of flakiness.
    return NotionClient(
        access_token="secret_test_token",
        rate_limit_rps=1000.0,
        rate_limit_burst=1000,
        transport=transport,
    )


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_validate_token_returns_workspace_info_and_pins_version_header():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "object": "user",
                "id": "bot-1",
                "type": "bot",
                "bot": {
                    "owner": {"type": "workspace", "workspace_id": "ws-xyz"},
                    "workspace_name": "Engineering",
                },
            },
        )

    client = _client_with_handler(handler)
    info = await client.validate_token()

    assert info.bot_id == "bot-1"
    assert info.workspace_id == "ws-xyz"
    assert info.workspace_name == "Engineering"

    assert len(captured) == 1
    request = captured[0]
    # Requests now flow through the SDK, which adds its own User-Agent alongside the
    # headers we care about. Assert the specific headers we pin rather than the full set.
    assert request.method == "GET"
    assert request.headers["Notion-Version"] == NOTION_API_VERSION
    assert request.headers["Authorization"] == "Bearer secret_test_token"
    assert request.headers["User-Agent"] == SDK_USER_AGENT
    assert str(request.url) == "https://api.notion.com/v1/users/me"


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_validate_token_401_raises_notion_auth_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"object": "error", "status": 401, "code": "unauthorized", "message": "API token invalid"},
        )

    client = _client_with_handler(handler)

    with pytest.raises(NotionAuthError) as excinfo:
        await client.validate_token()

    assert excinfo.value.status_code == 401
    assert excinfo.value.code == "unauthorized"


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_list_accessible_pages_extracts_titles_and_pagination():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "results": [
                    {
                        "object": "page",
                        "id": "page-1",
                        "url": "https://notion.so/page-1",
                        "last_edited_time": "2026-06-01T10:00:00.000Z",
                        "parent": {"type": "page_id", "page_id": "parent-1"},
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Roadmap"}, {"plain_text": " 2026"}],
                            }
                        },
                    },
                    # Mix in a data_source result that should be filtered out.
                    {"object": "data_source", "id": "ds-1"},
                    {
                        "object": "page",
                        "id": "page-2",
                        "url": "https://notion.so/page-2",
                        "last_edited_time": "2026-05-30T09:00:00.000Z",
                        "parent": {"type": "workspace", "workspace": True},
                        "properties": {"Name": {"type": "title", "title": []}},
                    },
                ],
                "next_cursor": "cursor-abc",
                "has_more": True,
            },
        )

    client = _client_with_handler(handler)
    page = await client.list_accessible_pages()

    assert page.has_more is True
    assert page.next_cursor == "cursor-abc"
    assert len(page.items) == 2
    assert page.items[0].notion_page_id == "page-1"
    assert page.items[0].title == "Roadmap 2026"
    assert page.items[0].parent_id == "parent-1"
    assert page.items[0].last_edited_time is not None
    assert page.items[1].title == ""
    assert page.items[1].parent_id is None

    # The SDK serializes search as a POST body. With no cursor, start_cursor is omitted
    # entirely (the SDK drops None cursors) rather than sent as null.
    first = captured[0]
    assert first.method == "POST"
    assert str(first.url) == "https://api.notion.com/v1/search"
    first_body = json.loads(first.content)
    assert first_body == {
        "filter": {"property": "object", "value": "page"},
        "sort": {"timestamp": "last_edited_time", "direction": "descending"},
        "page_size": 100,
    }
    assert "start_cursor" not in first_body

    await client.list_accessible_pages(cursor="cursor-abc")
    second_body = json.loads(captured[1].content)
    assert second_body["start_cursor"] == "cursor-abc"


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_get_block_children_returns_one_page_of_blocks():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "results": [
                    {"id": "b1", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": []}},
                    {"id": "b2", "type": "heading_1", "has_children": False, "heading_1": {"rich_text": []}},
                ],
                "next_cursor": None,
                "has_more": False,
            },
        )

    client = _client_with_handler(handler)
    result = await client.get_block_children("page-1")

    assert len(result.blocks) == 2
    assert result.blocks[0]["type"] == "paragraph"
    assert result.has_more is False
    assert result.next_cursor is None

    # With no cursor, start_cursor is omitted (not sent as null).
    first = captured[0]
    assert first.method == "GET"
    assert str(first.url) == "https://api.notion.com/v1/blocks/page-1/children?page_size=100"
    assert "start_cursor" not in first.url.params

    await client.get_block_children("page-1", cursor="cursor-xyz")
    assert captured[1].url.params["start_cursor"] == "cursor-xyz"
    assert captured[1].url.params["page_size"] == "100"


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_list_accessible_nodes_returns_pages_and_databases_unfiltered():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "results": [
                    {
                        "object": "page",
                        "id": "page-1",
                        "url": "https://notion.so/page-1",
                        "last_edited_time": "2026-06-01T10:00:00.000Z",
                        "parent": {"type": "page_id", "page_id": "parent-1"},
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Roadmap"}, {"plain_text": " 2026"}],
                            }
                        },
                    },
                    {
                        "object": "data_source",
                        "id": "ds-1",
                        "url": "https://notion.so/ds-1",
                        "last_edited_time": "2026-05-31T08:00:00.000Z",
                        # The data source's parent carries the owning database id (sibling key).
                        "parent": {"type": "workspace", "workspace": True, "database_id": "db-1"},
                        # Per the documented assumption, a data source's name lives in a
                        # top-level `title` rich-text array (not under `properties`).
                        "title": [{"plain_text": "Tasks"}, {"plain_text": " DB"}],
                    },
                    {
                        "object": "page",
                        "id": "page-2",
                        "url": "https://notion.so/page-2",
                        "last_edited_time": "2026-05-30T09:00:00.000Z",
                        "parent": {"type": "workspace", "workspace": True},
                        "properties": {"Name": {"type": "title", "title": []}},
                    },
                    {"object": "comment", "id": "c-1"},
                ],
                "next_cursor": "cursor-abc",
                "has_more": True,
            },
        )

    client = _client_with_handler(handler)
    page = await client.list_accessible_nodes()

    assert page.has_more is True
    assert page.next_cursor == "cursor-abc"
    assert len(page.nodes) == 3

    page_node = page.nodes[0]
    assert page_node.node_id == "page-1"
    assert page_node.kind == "page"
    assert page_node.title == "Roadmap 2026"
    assert page_node.parent_id == "parent-1"
    assert page_node.parent_kind == "page"
    # Search results carry no has_children flag for pages, so every page is treated
    # as expandable (see _node_from_search_result); a genuine leaf reveals
    # "No pages inside" on lazy expansion.
    assert page_node.has_children is True

    db_node = page.nodes[1]
    assert db_node.kind == "database"
    # Normalized up to the owning database id, not the data-source id.
    assert db_node.node_id == "db-1"
    assert db_node.title == "Tasks DB"
    assert db_node.has_children is True

    top_node = page.nodes[2]
    assert top_node.node_id == "page-2"
    assert top_node.title == ""
    assert top_node.parent_id is None
    assert top_node.parent_kind == "workspace"

    # Search runs UNFILTERED (no `filter` body param) so data sources surface.
    first = captured[0]
    assert first.method == "POST"
    assert str(first.url) == "https://api.notion.com/v1/search"
    first_body = json.loads(first.content)
    assert "filter" not in first_body
    assert first_body["sort"] == {"timestamp": "last_edited_time", "direction": "descending"}
    assert first_body["page_size"] == 100
    assert "start_cursor" not in first_body

    await client.list_accessible_nodes(cursor="cursor-abc")
    second_body = json.loads(captured[1].content)
    assert second_body["start_cursor"] == "cursor-abc"


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_list_child_nodes_filters_block_children_and_paginates():
    pages: dict[str | None, dict[str, Any]] = {
        None: {
            "object": "list",
            "results": [
                {"id": "b1", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": []}},
                {
                    "id": "child-page-1",
                    "type": "child_page",
                    "has_children": True,
                    "child_page": {"title": "Subpage"},
                },
                {
                    "id": "child-db-1",
                    "type": "child_database",
                    "has_children": False,
                    "child_database": {"title": "Embedded DB"},
                },
            ],
            "next_cursor": "next-1",
            "has_more": True,
        },
        "next-1": {
            "object": "list",
            "results": [
                {
                    "id": "child-page-2",
                    "type": "child_page",
                    "has_children": False,
                    "child_page": {"title": "Another Subpage"},
                },
            ],
            "next_cursor": None,
            "has_more": False,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("start_cursor")
        return httpx.Response(200, json=pages[cursor])

    client = _client_with_handler(handler)
    first = await client.list_child_nodes("parent-page")

    assert first.has_more is True
    assert first.next_cursor == "next-1"
    assert len(first.nodes) == 2
    assert first.nodes[0].node_id == "child-page-1"
    assert first.nodes[0].kind == "page"
    assert first.nodes[0].title == "Subpage"
    assert first.nodes[0].has_children is True
    assert first.nodes[1].node_id == "child-db-1"
    assert first.nodes[1].kind == "database"
    assert first.nodes[1].title == "Embedded DB"
    assert first.nodes[1].has_children is True

    second = await client.list_child_nodes("parent-page", cursor="next-1")
    assert second.has_more is False
    assert len(second.nodes) == 1
    assert second.nodes[0].node_id == "child-page-2"
    assert second.nodes[0].has_children is False


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_get_database_then_query_data_source_lists_rows():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        path = request.url.path
        if path == "/v1/databases/db-1":
            return httpx.Response(
                200,
                json={
                    "object": "database",
                    "id": "db-1",
                    "title": [{"plain_text": "Projects"}],
                    "data_sources": [
                        {"id": "ds-1", "name": "Primary"},
                        {"id": "ds-2", "name": "Secondary"},
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "object": "list",
                "results": [
                    {"object": "page", "id": "row-1"},
                    {"object": "page", "id": "row-2"},
                ],
                "next_cursor": "rows-next",
                "has_more": True,
            },
        )

    client = _client_with_handler(handler)
    info = await client.get_database("db-1")
    assert info.database_id == "db-1"
    assert info.title == "Projects"
    assert [s.data_source_id for s in info.data_sources] == ["ds-1", "ds-2"]
    assert info.data_sources[0].name == "Primary"

    rows_page = await client.query_data_source("ds-1")
    assert [r["id"] for r in rows_page.rows] == ["row-1", "row-2"]
    assert rows_page.has_more is True
    assert rows_page.next_cursor == "rows-next"

    db_request = captured[0]
    assert db_request.method == "GET"
    assert str(db_request.url) == "https://api.notion.com/v1/databases/db-1"

    query_request = captured[1]
    assert query_request.method == "POST"
    assert str(query_request.url) == "https://api.notion.com/v1/data_sources/ds-1/query"
    query_body = json.loads(query_request.content)
    assert query_body["page_size"] == 100
    assert "start_cursor" not in query_body

    await client.query_data_source("ds-1", cursor="rows-next")
    paginated_body = json.loads(captured[2].content)
    assert paginated_body["start_cursor"] == "rows-next"


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_resolve_containing_page_walks_block_parent_chain():
    captured: list[httpx.Request] = []

    # block-a's parent is block-b (a column), whose parent is the owning page.
    parents: dict[str, dict[str, Any]] = {
        "block-a": {"type": "block_id", "block_id": "block-b"},
        "block-b": {"type": "page_id", "page_id": "owning-page"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        block_id = request.url.path.split("/")[3]
        return httpx.Response(200, json={"object": "block", "id": block_id, "parent": parents[block_id]})

    client = _client_with_handler(handler)
    resolved = await client.resolve_containing_page("block-a")

    assert resolved == "owning-page"
    assert [r.url.path.split("/")[3] for r in captured] == ["block-a", "block-b"]


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_extract_parent_normalizes_data_source_and_handles_edge_cases():
    assert _extract_parent({"type": "data_source_id", "data_source_id": "ds-1", "database_id": "db-1"}) == (
        "db-1",
        "database",
    )

    assert _extract_parent({"type": "page_id", "page_id": "p-1"}) == ("p-1", "page")
    assert _extract_parent({"type": "database_id", "database_id": "db-2"}) == ("db-2", "database")

    assert _extract_parent({"type": "workspace", "workspace": True}) == (None, "workspace")

    assert _extract_parent({"type": "agent_id", "agent_id": "agent-1"}) == (None, None)

    assert _extract_parent({"type": "block_id", "block_id": "blk-1"}) == ("blk-1", "block")


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_list_accessible_nodes_workspace_and_agent_parents_yield_no_edge():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "object": "list",
                "results": [
                    {
                        "object": "page",
                        "id": "page-ws",
                        "parent": {"type": "workspace", "workspace": True},
                        "properties": {"Name": {"type": "title", "title": [{"plain_text": "Top"}]}},
                    },
                    {
                        "object": "page",
                        "id": "page-agent",
                        "parent": {"type": "agent_id", "agent_id": "agent-1"},
                        "properties": {"Name": {"type": "title", "title": [{"plain_text": "Agent Page"}]}},
                    },
                ],
                "next_cursor": None,
                "has_more": False,
            },
        )

    client = _client_with_handler(handler)
    page = await client.list_accessible_nodes()

    ws_node = next(n for n in page.nodes if n.node_id == "page-ws")
    assert ws_node.parent_id is None
    assert ws_node.parent_kind == "workspace"

    agent_node = next(n for n in page.nodes if n.node_id == "page-agent")
    assert agent_node.parent_id is None
    assert agent_node.parent_kind is None


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_rate_limit_429_is_retried_with_retry_after():
    # This test could not be recorded against a real workspace deterministically
    # (Notion's 429 is throttled by their infra and hard to provoke). We exercise
    # the retry path with a scripted MockTransport instead.
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"object": "error", "status": 429, "code": "rate_limited", "message": "Rate limited."},
            )
        return httpx.Response(
            200,
            json={
                "object": "user",
                "id": "bot-1",
                "type": "bot",
                "bot": {
                    "owner": {"type": "workspace", "workspace_id": "ws-1"},
                    "workspace_name": "Acme",
                },
            },
        )

    client = _client_with_handler(handler)
    info = await client.validate_token()
    assert info.bot_id == "bot-1"
    assert call_count["n"] == 2


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_unexpected_4xx_raises_notion_api_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"object": "error", "status": 400, "code": "validation_error", "message": "bad request"},
        )

    client = _client_with_handler(handler)
    with pytest.raises(NotionAPIError) as excinfo:
        await client.get_page("page-1")
    assert excinfo.value.code == "validation_error"
    assert excinfo.value.status_code == 400


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_walk_page_blocks_yields_in_document_order_and_dedupes_synced_duplicates():
    # Tree:
    #   page-root → [p1, toggle(t1)]
    #   t1 → [synced-original (orig-id), p-under-toggle]
    #   orig-id (children of original synced block) → [sp1]
    #   And then a duplicate synced block pointing at orig-id appears later — its
    #   children must NOT be re-walked.

    pages: dict[str, list[dict[str, Any]]] = {
        "page-root": [
            {"id": "p1", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": []}},
            {"id": "t1", "type": "toggle", "has_children": True, "toggle": {"rich_text": []}},
            {
                "id": "dup-1",
                "type": "synced_block",
                "has_children": True,
                "synced_block": {"synced_from": {"block_id": "orig-id"}},
            },
        ],
        "t1": [
            {
                "id": "orig-id",
                "type": "synced_block",
                "has_children": True,
                "synced_block": {"synced_from": None},
            },
            {
                "id": "p-under-toggle",
                "type": "paragraph",
                "has_children": False,
                "paragraph": {"rich_text": []},
            },
        ],
        "orig-id": [
            {"id": "sp1", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": []}},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        segments = request.url.path.split("/")
        block_id = segments[3]
        results = pages.get(block_id, [])
        return httpx.Response(200, json={"object": "list", "results": results, "next_cursor": None, "has_more": False})

    client = _client_with_handler(handler)
    emitted: list[dict[str, Any]] = []
    async for block in client.walk_page_blocks("page-root"):
        emitted.append(block)

    emitted_ids = [b["id"] for b in emitted]
    # Order: p1, t1, (children of t1: orig-id, then orig-id's children sp1, then p-under-toggle), dup-1
    assert emitted_ids == ["p1", "t1", "orig-id", "sp1", "p-under-toggle", "dup-1"]
    # The duplicate must be flagged so the converter can skip it.
    dup = next(b for b in emitted if b["id"] == "dup-1")
    assert dup.get("_synced_duplicate") is True
    assert next(b for b in emitted if b["id"] == "p1")["_depth"] == 0
    assert next(b for b in emitted if b["id"] == "orig-id")["_depth"] == 1
    assert next(b for b in emitted if b["id"] == "sp1")["_depth"] == 2


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_walk_page_blocks_groups_table_rows_onto_table_block():
    # The walker fetches the table's table_row children and stashes their payloads on the
    # table block as `_table_rows`; it must NOT emit the rows as standalone blocks.
    def _cell(text: str) -> list[dict[str, Any]]:
        return [
            {
                "type": "text",
                "text": {"content": text, "link": None},
                "plain_text": text,
                "href": None,
                "annotations": {
                    "bold": False,
                    "italic": False,
                    "strikethrough": False,
                    "underline": False,
                    "code": False,
                    "color": "default",
                },
            }
        ]

    pages: dict[str, list[dict[str, Any]]] = {
        "page-root": [
            {
                "id": "table-1",
                "type": "table",
                "has_children": True,
                "table": {"table_width": 2, "has_column_header": True, "has_row_header": False},
            },
            {"id": "after", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": []}},
        ],
        "table-1": [
            {
                "id": "row-1",
                "type": "table_row",
                "has_children": False,
                "table_row": {"cells": [_cell("A"), _cell("B")]},
            },
            {
                "id": "row-2",
                "type": "table_row",
                "has_children": False,
                "table_row": {"cells": [_cell("1"), _cell("2")]},
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        block_id = request.url.path.split("/")[3]
        results = pages.get(block_id, [])
        return httpx.Response(200, json={"object": "list", "results": results, "next_cursor": None, "has_more": False})

    client = _client_with_handler(handler)
    emitted = [block async for block in client.walk_page_blocks("page-root")]

    emitted_ids = [b["id"] for b in emitted]
    assert emitted_ids == ["table-1", "after"]
    assert all(b["type"] != "table_row" for b in emitted)

    table = next(b for b in emitted if b["id"] == "table-1")
    assert table["_table_rows"] == [
        {"cells": [_cell("A"), _cell("B")]},
        {"cells": [_cell("1"), _cell("2")]},
    ]

    assert blocks_to_text([table]) == "\n".join(["| A | B |", "| --- | --- |", "| 1 | 2 |"])


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_walk_then_convert_end_to_end_smoke():
    # Lightweight integration between the walker and the converter so we're sure
    # the augmented `_depth` and `_synced_duplicate` keys round-trip cleanly.
    def handler(request: httpx.Request) -> httpx.Response:
        segments = request.url.path.split("/")
        block_id = segments[3]
        if block_id == "root":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "results": [
                        {
                            "id": "h",
                            "type": "heading_1",
                            "has_children": False,
                            "heading_1": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": "Hi", "link": None},
                                        "plain_text": "Hi",
                                        "href": None,
                                        "annotations": {
                                            "bold": False,
                                            "italic": False,
                                            "strikethrough": False,
                                            "underline": False,
                                            "code": False,
                                            "color": "default",
                                        },
                                    }
                                ]
                            },
                        }
                    ],
                    "next_cursor": None,
                    "has_more": False,
                },
            )
        return httpx.Response(200, json={"results": [], "next_cursor": None, "has_more": False})

    client = _client_with_handler(handler)
    collected = [block async for block in client.walk_page_blocks("root")]
    assert blocks_to_text(collected) == "# Hi"
