from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.collaboration.live import LiveDocument, LiveDocumentFilters, LiveDocumentUpdate
from app.models.collaboration.workspace import Attachment
from app.models.workspaces.documents import Document
from infra.jobs import Job
from integrations.notion.client import (
    NotionAPIError,
    NotionAuthError,
    NotionChildNode,
    NotionChildNodeListPage,
    NotionDatabaseInfo,
    NotionDataSourceQueryPage,
    NotionDataSourceRef,
    NotionPageMetadata,
)
from integrations.notion.enums import NotionNodeKind
from integrations.notion.jobs import CascadeNotionSelectionJob, SyncNotionPagesJob
from integrations.notion.models import NotionPage
from tests.helpers.factories import create_document, create_notion_connection, create_notion_page, create_user


def _child(node_id: str, kind: str, *, title: str = "", has_children: bool = False) -> NotionChildNode:
    return NotionChildNode(node_id=node_id, kind=kind, title=title, has_children=has_children)


def _children_returning(children_by_parent: dict[str, list[NotionChildNode]]):
    async def list_child_nodes(self, parent_id: str, cursor: str | None = None) -> NotionChildNodeListPage:
        return NotionChildNodeListPage(
            nodes=children_by_parent.get(parent_id, []),
            next_cursor=None,
            has_more=False,
        )

    return list_child_nodes


def _database_returning(data_sources_by_db: dict[str, list[str]]):
    async def get_database(self, database_id: str) -> NotionDatabaseInfo:
        return NotionDatabaseInfo(
            database_id=database_id,
            title="DB",
            data_sources=[
                NotionDataSourceRef(data_source_id=source_id, name=None)
                for source_id in data_sources_by_db.get(database_id, [])
            ],
        )

    return get_database


def _query_returning(rows_by_source: dict[str, list[str]]):
    async def query_data_source(self, data_source_id: str, cursor: str | None = None) -> NotionDataSourceQueryPage:
        return NotionDataSourceQueryPage(
            rows=[{"id": row_id, "object": "page"} for row_id in rows_by_source.get(data_source_id, [])],
            next_cursor=None,
            has_more=False,
        )

    return query_data_source


def _heading_block(text: str, *, block_id: str = "block-1") -> dict[str, Any]:
    return {
        "id": block_id,
        "type": "heading_1",
        "_depth": 0,
        "has_children": False,
        "heading_1": {
            "rich_text": [
                {
                    "type": "text",
                    "plain_text": text,
                    "text": {"content": text, "link": None},
                    "annotations": {
                        "bold": False,
                        "italic": False,
                        "strikethrough": False,
                        "code": False,
                    },
                }
            ]
        },
    }


def _metadata(notion_page_id: str, *, title: str, parent_id: str | None = "workspace") -> NotionPageMetadata:
    return NotionPageMetadata(
        notion_page_id=notion_page_id,
        title=title,
        parent_id=parent_id,
        last_edited_time=datetime(2026, 5, 1, tzinfo=UTC),
        url=f"https://notion.so/{notion_page_id}",
    )


def _walk_returning(blocks_by_page: dict[str, list[dict[str, Any]]]):
    """Build an async-iterator factory mock for NotionClient.walk_page_blocks."""

    def factory(page_id: str) -> AsyncIterator[dict[str, Any]]:
        async def gen() -> AsyncIterator[dict[str, Any]]:
            for block in blocks_by_page.get(page_id, []):
                yield block

        return gen()

    return factory


@pytest.mark.asyncio
async def test_sync_syncs_only_selected_pages_and_records_content_and_timestamp():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    selected_a = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-a",
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )
    selected_b = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-b",
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )
    unselected = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-c",
        is_selected_for_sync=False,
        content_text=None,
        last_synced_at=None,
    )

    metadata_by_page = {
        "page-a": _metadata("page-a", title="Page A Refreshed"),
        "page-b": _metadata("page-b", title="Page B Refreshed"),
    }
    blocks_by_page = {
        "page-a": [_heading_block("Alpha", block_id="b-a")],
        "page-b": [_heading_block("Bravo", block_id="b-b")],
    }

    with (
        patch(
            "integrations.notion.jobs.NotionClient.get_page",
            AsyncMock(side_effect=lambda page_id: metadata_by_page[page_id]),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.walk_page_blocks",
            side_effect=_walk_returning(blocks_by_page),
        ),
    ):
        await SyncNotionPagesJob(user_id=user.id).perform()

    await selected_a.refresh_from_db()
    await selected_b.refresh_from_db()
    await unselected.refresh_from_db()

    assert selected_a.content_text == "# Alpha"
    assert selected_a.title == "Page A Refreshed"
    assert selected_a.last_synced_at is not None
    assert selected_a.notion_last_edited_time == datetime(2026, 5, 1, tzinfo=UTC)

    assert selected_b.content_text == "# Bravo"
    assert selected_b.title == "Page B Refreshed"
    assert selected_b.last_synced_at is not None

    assert unselected.content_text is None
    assert unselected.last_synced_at is None


@pytest.mark.asyncio
async def test_sync_bails_on_auth_error_and_leaves_subsequent_pages_untouched():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    page_one = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-1",
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )
    page_two = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-2",
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )

    with patch(
        "integrations.notion.jobs.NotionClient.get_page",
        AsyncMock(side_effect=NotionAuthError(401, "unauthorized", "bad token")),
    ):
        await SyncNotionPagesJob(user_id=user.id).perform()

    await page_one.refresh_from_db()
    await page_two.refresh_from_db()

    # Auth error on the first page aborts the entire run; nothing was mutated.
    assert page_one.last_synced_at is None
    assert page_one.content_text is None
    assert page_two.last_synced_at is None
    assert page_two.content_text is None


@pytest.mark.asyncio
async def test_sync_marks_404_page_inaccessible_and_keeps_syncing_others():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    # Pages are ordered by -updated_at; create the 404 page first so the other is processed too.
    missing_page = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-missing",
        is_selected_for_sync=True,
        content_text="stale content",
        last_synced_at=None,
    )
    healthy_page = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-healthy",
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )

    async def get_page(page_id: str):
        if page_id == "page-missing":
            raise NotionAPIError(404, "object_not_found", "gone")
        return _metadata(page_id, title="Healthy Refreshed")

    with (
        patch("integrations.notion.jobs.NotionClient.get_page", AsyncMock(side_effect=get_page)),
        patch(
            "integrations.notion.jobs.NotionClient.walk_page_blocks",
            side_effect=_walk_returning({"page-healthy": [_heading_block("Healthy", block_id="b-h")]}),
        ),
    ):
        await SyncNotionPagesJob(user_id=user.id).perform()

    await missing_page.refresh_from_db()
    await healthy_page.refresh_from_db()

    # 404 page: marked synced with empty content; row is NOT deleted.
    assert missing_page.content_text == ""
    assert missing_page.last_synced_at is not None
    assert await NotionPage.filter(id=missing_page.id).count() == 1

    assert healthy_page.content_text == "# Healthy"
    assert healthy_page.title == "Healthy Refreshed"
    assert healthy_page.last_synced_at is not None


@pytest.mark.asyncio
async def test_sync_imports_selected_pages_as_documents():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    with_content = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-doc",
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )
    empty = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-empty",
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )

    metadata_by_page = {
        "page-doc": _metadata("page-doc", title="Imported Doc"),
        "page-empty": _metadata("page-empty", title="Empty Doc"),
    }
    blocks_by_page = {"page-doc": [_heading_block("Imported", block_id="b-doc")]}

    with (
        patch(
            "integrations.notion.jobs.NotionClient.get_page",
            AsyncMock(side_effect=lambda page_id: metadata_by_page[page_id]),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.walk_page_blocks",
            side_effect=_walk_returning(blocks_by_page),
        ),
    ):
        await SyncNotionPagesJob(user_id=user.id).perform()

    await with_content.refresh_from_db()
    await empty.refresh_from_db()

    assert with_content.document_id is not None
    content_document = await Document.get(id=with_content.document_id)
    assert content_document.title == "Imported Doc"
    assert content_document.organization_id == user.organization_id
    assert content_document.creator_id == user.id
    assert await content_document.get_live_document_markdown() == "# Imported"

    assert empty.document_id is not None
    empty_document = await Document.get(id=empty.document_id)
    assert empty_document.title == "Empty Doc"
    assert await empty_document.get_live_document_markdown() == ""


@pytest.mark.asyncio
async def test_sync_import_is_idempotent_across_reruns():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    page = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-once",
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )

    metadata_by_page = {"page-once": _metadata("page-once", title="First Title")}
    blocks_by_page = {"page-once": [_heading_block("First", block_id="b-once")]}

    with (
        patch(
            "integrations.notion.jobs.NotionClient.get_page",
            AsyncMock(side_effect=lambda page_id: metadata_by_page[page_id]),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.walk_page_blocks",
            side_effect=_walk_returning(blocks_by_page),
        ),
    ):
        await SyncNotionPagesJob(user_id=user.id).perform()

    await page.refresh_from_db()
    document_id = page.document_id
    assert document_id is not None
    document = await Document.get(id=document_id)
    updates_after_first = await LiveDocumentUpdate.filter(
        LiveDocumentFilters.for_topic(document.live_document_topic)
    ).count()

    # The page content and title both change in Notion; the Document must not be touched.
    metadata_by_page = {"page-once": _metadata("page-once", title="Renamed Title")}
    blocks_by_page = {"page-once": [_heading_block("Second", block_id="b-once-2")]}

    with (
        patch(
            "integrations.notion.jobs.NotionClient.get_page",
            AsyncMock(side_effect=lambda page_id: metadata_by_page[page_id]),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.walk_page_blocks",
            side_effect=_walk_returning(blocks_by_page),
        ),
    ):
        await SyncNotionPagesJob(user_id=user.id).perform()

    await page.refresh_from_db()

    # content_text refreshes (existing behavior) but the Document is frozen at import time.
    assert page.content_text == "# Second"
    assert page.document_id == document_id
    assert await Document.filter(notion_pages__id=page.id).count() == 1
    document = await Document.get(id=document_id)
    assert document.title == "First Title"
    assert await document.get_live_document_markdown() == "# First"
    updates_after_second = await LiveDocumentUpdate.filter(
        LiveDocumentFilters.for_topic(document.live_document_topic)
    ).count()
    assert updates_after_second == updates_after_first


@pytest.mark.asyncio
async def test_sync_skips_deselected_page_and_leaves_imported_document_untouched():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    # A page that was imported once, then deselected. Sync must skip it entirely.
    document = await create_document(organization_id=user.organization_id, creator_id=user.id, title="Frozen Title")
    await LiveDocument.set_initial_content(document.live_document_topic, "# Frozen body")
    synced_at = datetime(2026, 4, 1, tzinfo=UTC)
    deselected = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-deselected",
        is_selected_for_sync=False,
        content_text="# Frozen body",
        last_synced_at=synced_at,
        document_id=document.id,
    )

    # If the job ever touched a deselected page, these mocks would feed it new data.
    with (
        patch(
            "integrations.notion.jobs.NotionClient.get_page",
            AsyncMock(side_effect=lambda page_id: _metadata(page_id, title="Should Not Apply")),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.walk_page_blocks",
            side_effect=_walk_returning({"page-deselected": [_heading_block("Should Not Apply", block_id="nope")]}),
        ),
    ):
        await SyncNotionPagesJob(user_id=user.id).perform()

    await deselected.refresh_from_db()

    assert deselected.content_text == "# Frozen body"
    assert deselected.last_synced_at == synced_at
    assert deselected.document_id == document.id

    assert await Document.filter(notion_pages__id=deselected.id).count() == 1
    document = await Document.get(id=document.id)
    assert document.title == "Frozen Title"
    assert await document.get_live_document_markdown() == "# Frozen body"


def _image_block(block_id: str, url: str) -> dict[str, Any]:
    return {
        "id": block_id,
        "type": "image",
        "_depth": 0,
        "has_children": False,
        "image": {"caption": [], "type": "file", "file": {"url": url}},
    }


def _file_block(block_id: str, url: str, name: str) -> dict[str, Any]:
    return {
        "id": block_id,
        "type": "file",
        "_depth": 0,
        "has_children": False,
        "file": {"caption": [], "type": "file", "file": {"url": url}, "name": name},
    }


@pytest.mark.asyncio
async def test_sync_seeds_document_with_original_notion_media_urls():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    page = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-media",
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )

    blocks_by_page = {
        "page-media": [
            _heading_block("Media Doc", block_id="b-head"),
            _image_block("img-1", "https://s3/diagram.png"),
            _file_block("file-1", "https://s3/report.pdf", "report.pdf"),
        ]
    }

    with (
        patch(
            "integrations.notion.jobs.NotionClient.get_page",
            AsyncMock(side_effect=lambda page_id: _metadata(page_id, title="Media Doc")),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.walk_page_blocks",
            side_effect=_walk_returning(blocks_by_page),
        ),
    ):
        await SyncNotionPagesJob(user_id=user.id).perform()

    await page.refresh_from_db()
    assert page.document_id is not None
    document = await Document.get(id=page.document_id)

    markdown = await document.get_live_document_markdown()
    # Media references the original Notion URLs directly — no re-hosting, no proxy URLs.
    assert markdown.startswith("# Media Doc")
    assert "![](https://s3/diagram.png)" in markdown
    assert "[report.pdf](https://s3/report.pdf)" in markdown

    # Proof that re-hosting is gone: no Attachment rows were created for the workspace.
    assert await Attachment.filter(workspace_id=document.workspace_id) == []


@pytest.mark.asyncio
async def test_sync_returns_without_raising_when_connection_missing():
    # No NotionConnection exists for this user — simulates the disconnect-race
    # between enqueue and run. Must not raise.
    missing_user_id = uuid4()

    await SyncNotionPagesJob(user_id=missing_user_id).perform()


@pytest.mark.asyncio
async def test_sync_never_imports_a_database_row_flagged_for_sync():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    # A folder (database) row mistakenly flagged for sync must never reach the import path.
    folder = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="db-1",
        kind=NotionNodeKind.DATABASE.value,
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )
    leaf = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-leaf",
        kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=True,
        content_text=None,
        last_synced_at=None,
    )

    get_page = AsyncMock(side_effect=lambda page_id: _metadata(page_id, title="Leaf Refreshed"))
    with (
        patch("integrations.notion.jobs.NotionClient.get_page", get_page),
        patch(
            "integrations.notion.jobs.NotionClient.walk_page_blocks",
            side_effect=_walk_returning({"page-leaf": [_heading_block("Leaf", block_id="b-leaf")]}),
        ),
    ):
        await SyncNotionPagesJob(user_id=user.id).perform()

    # get_page is only ever called for the page leaf, never the database row.
    assert [call.args[0] for call in get_page.await_args_list] == ["page-leaf"]

    await folder.refresh_from_db()
    await leaf.refresh_from_db()
    assert folder.content_text is None
    assert folder.last_synced_at is None
    assert leaf.content_text == "# Leaf"


@pytest.mark.asyncio
async def test_cascade_page_folder_selects_all_nested_leaves():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    root = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="root-page",
        kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=False,
    )

    # root-page -> child-1 (page) -> grandchild (page); root-page -> child-2 (page)
    children = {
        "root-page": [_child("child-1", "page", title="Child 1"), _child("child-2", "page", title="Child 2")],
        "child-1": [_child("grandchild", "page", title="Grandchild")],
        "child-2": [],
        "grandchild": [],
    }

    with patch(
        "integrations.notion.jobs.NotionClient.list_child_nodes",
        autospec=True,
        side_effect=_children_returning(children),
    ):
        await CascadeNotionSelectionJob(
            user_id=user.id, node_id="root-page", kind=NotionNodeKind.PAGE.value, selected=True
        ).perform()

    selected_ids = {
        page.notion_page_id
        for page in await NotionPage.filter(notion_connection_id=connection.id, is_selected_for_sync=True)
    }
    assert selected_ids == {"root-page", "child-1", "child-2", "grandchild"}

    await root.refresh_from_db()
    assert root.counts_authoritative is True
    assert root.total_descendant_count == 3
    assert root.selected_descendant_count == 3

    # A cascade walks the whole subtree, so descendant folders are fully known and become
    # authoritative too — not just the root. Without this the client renders them "indeterminate"
    # (tri-state short-circuits on counts_authoritative) and the cascade appears not to apply.
    child_1 = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="child-1")
    assert child_1.counts_authoritative is True
    assert child_1.total_descendant_count == 1
    assert child_1.selected_descendant_count == 1


@pytest.mark.asyncio
async def test_cascade_database_folder_walks_data_sources_to_rows():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="db-root",
        kind=NotionNodeKind.DATABASE.value,
        is_selected_for_sync=False,
    )

    data_sources = {"db-root": ["source-a", "source-b"]}
    rows = {"source-a": ["row-1", "row-2"], "source-b": ["row-3"]}
    children: dict[str, list[NotionChildNode]] = {"row-1": [], "row-2": [], "row-3": []}

    with (
        patch(
            "integrations.notion.jobs.NotionClient.get_database",
            autospec=True,
            side_effect=_database_returning(data_sources),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.query_data_source",
            autospec=True,
            side_effect=_query_returning(rows),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.list_child_nodes",
            autospec=True,
            side_effect=_children_returning(children),
        ),
    ):
        await CascadeNotionSelectionJob(
            user_id=user.id, node_id="db-root", kind=NotionNodeKind.DATABASE.value, selected=True
        ).perform()

    selected_ids = {
        page.notion_page_id
        for page in await NotionPage.filter(notion_connection_id=connection.id, is_selected_for_sync=True)
    }
    # The database itself is not a leaf — only its rows are selected.
    assert selected_ids == {"row-1", "row-2", "row-3"}

    db_root = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="db-root")
    assert db_root.is_selected_for_sync is False
    assert db_root.counts_authoritative is True
    assert db_root.total_descendant_count == 3
    assert db_root.selected_descendant_count == 3


@pytest.mark.asyncio
async def test_cascade_deselect_clears_subtree_wholesale():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    root = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="root-page",
        kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=True,
    )
    # child-1 is itself a folder (parents a grandchild), so the de-select must also leave it
    # authoritative — otherwise its tri-state checkbox stays "indeterminate" and looks un-cleared.
    child = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="child-1",
        kind=NotionNodeKind.PAGE.value,
        parent_notion_id="root-page",
        parent_kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=True,
    )
    grandchild = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="grandchild",
        kind=NotionNodeKind.PAGE.value,
        parent_notion_id="child-1",
        parent_kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=True,
    )

    children = {
        "root-page": [_child("child-1", "page", title="Child 1")],
        "child-1": [_child("grandchild", "page", title="Grandchild")],
        "grandchild": [],
    }

    with patch(
        "integrations.notion.jobs.NotionClient.list_child_nodes",
        autospec=True,
        side_effect=_children_returning(children),
    ):
        await CascadeNotionSelectionJob(
            user_id=user.id, node_id="root-page", kind=NotionNodeKind.PAGE.value, selected=False
        ).perform()

    await root.refresh_from_db()
    await child.refresh_from_db()
    await grandchild.refresh_from_db()
    assert root.is_selected_for_sync is False
    assert child.is_selected_for_sync is False
    assert grandchild.is_selected_for_sync is False
    assert root.selected_descendant_count == 0
    assert root.total_descendant_count == 2
    # The descendant folder is cleared and authoritative — the regression this guards against.
    assert child.counts_authoritative is True
    assert child.selected_descendant_count == 0
    assert child.total_descendant_count == 1


@pytest.mark.asyncio
async def test_cascade_guards_against_cycles():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="a",
        kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=False,
    )

    # a -> b -> a (cycle). The seen-set must stop infinite recursion.
    children = {"a": [_child("b", "page", title="B")], "b": [_child("a", "page", title="A")]}

    with patch(
        "integrations.notion.jobs.NotionClient.list_child_nodes",
        autospec=True,
        side_effect=_children_returning(children),
    ):
        await CascadeNotionSelectionJob(
            user_id=user.id, node_id="a", kind=NotionNodeKind.PAGE.value, selected=True
        ).perform()

    selected_ids = {
        page.notion_page_id
        for page in await NotionPage.filter(notion_connection_id=connection.id, is_selected_for_sync=True)
    }
    assert selected_ids == {"a", "b"}


@pytest.mark.asyncio
async def test_cascade_persists_discovered_descendants_with_kind_and_parent_kind():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="root-page",
        kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=False,
    )

    # root-page -> sub-db (database) -> row-1 (page)
    children = {"root-page": [_child("sub-db", "database", title="Sub DB")]}
    data_sources = {"sub-db": ["src"]}
    rows = {"src": ["row-1"]}
    children["row-1"] = []

    with (
        patch(
            "integrations.notion.jobs.NotionClient.list_child_nodes",
            autospec=True,
            side_effect=_children_returning(children),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.get_database",
            autospec=True,
            side_effect=_database_returning(data_sources),
        ),
        patch(
            "integrations.notion.jobs.NotionClient.query_data_source",
            autospec=True,
            side_effect=_query_returning(rows),
        ),
    ):
        await CascadeNotionSelectionJob(
            user_id=user.id, node_id="root-page", kind=NotionNodeKind.PAGE.value, selected=True
        ).perform()

    sub_db = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="sub-db")
    assert sub_db.kind == NotionNodeKind.DATABASE.value
    assert sub_db.parent_notion_id == "root-page"
    assert sub_db.parent_kind == NotionNodeKind.PAGE.value
    assert sub_db.is_selected_for_sync is False  # folder rows are never flagged

    row = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="row-1")
    assert row.kind == NotionNodeKind.PAGE.value
    assert row.parent_notion_id == "sub-db"
    assert row.parent_kind == NotionNodeKind.DATABASE.value
    assert row.is_selected_for_sync is True


@pytest.mark.asyncio
async def test_cascade_marks_node_inaccessible_on_404():
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="root-page",
        kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=False,
    )

    children = {"root-page": [_child("gone", "page", title="Gone")]}

    async def list_child_nodes(self, parent_id: str, cursor: str | None = None) -> NotionChildNodeListPage:
        if parent_id == "gone":
            raise NotionAPIError(404, "object_not_found", "gone")
        return NotionChildNodeListPage(nodes=children.get(parent_id, []), next_cursor=None, has_more=False)

    with patch("integrations.notion.jobs.NotionClient.list_child_nodes", autospec=True, side_effect=list_child_nodes):
        await CascadeNotionSelectionJob(
            user_id=user.id, node_id="root-page", kind=NotionNodeKind.PAGE.value, selected=True
        ).perform()

    gone = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="gone")
    # 404'd node is marked inaccessible (empty content + synced timestamp) and not selected.
    assert gone.content_text == ""
    assert gone.last_synced_at is not None
    assert gone.is_selected_for_sync is False

    root = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="root-page")
    assert root.is_selected_for_sync is True


@pytest.mark.asyncio
async def test_cascade_records_terminal_job_state_for_polling():

    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="root-page",
        kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=False,
    )

    definition = CascadeNotionSelectionJob(
        user_id=user.id, node_id="root-page", kind=NotionNodeKind.PAGE.value, selected=True
    )
    job = await Job.create_by_job_definition(definition)
    assert job.completed_at is None

    with patch(
        "integrations.notion.jobs.NotionClient.list_child_nodes",
        autospec=True,
        side_effect=_children_returning({"root-page": []}),
    ):
        await job.run()

    await job.refresh_from_db()
    # Phase 3 reads cascade state back via Job.by_job_definition(...).first().status.
    latest = await Job.by_job_definition(definition).order_by("-created_at").first()
    assert latest is not None
    assert latest.completed_at is not None
    assert latest.error is None


@pytest.mark.asyncio
async def test_cascade_refreshes_persisted_ancestor_counts_without_claiming_authority():
    # Cascading from a mid-tree node must walk the persisted parent chain above the resolved root
    # and refresh those ancestors' counts (without marking them authoritative — only one branch was
    # walked). This exercises the ancestor loop's reliance on parent_notion_id, the field most at
    # risk of being silently dropped from the _refresh_counts projection.
    user = await create_user()
    connection = await create_notion_connection(user_id=user.id)
    grandparent = await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="grandparent",
        kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=False,
    )
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="parent",
        kind=NotionNodeKind.PAGE.value,
        parent_notion_id="grandparent",
        parent_kind=NotionNodeKind.PAGE.value,
        is_selected_for_sync=False,
    )

    # Walk only from "parent" downward; "grandparent" is an unwalked ancestor above the resolved root.
    children = {
        "parent": [_child("leaf-1", "page", title="Leaf 1"), _child("leaf-2", "page", title="Leaf 2")],
        "leaf-1": [],
        "leaf-2": [],
    }

    with patch(
        "integrations.notion.jobs.NotionClient.list_child_nodes",
        autospec=True,
        side_effect=_children_returning(children),
    ):
        await CascadeNotionSelectionJob(
            user_id=user.id, node_id="parent", kind=NotionNodeKind.PAGE.value, selected=True
        ).perform()

    parent = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="parent")
    assert parent.counts_authoritative is True
    assert parent.total_descendant_count == 2
    assert parent.selected_descendant_count == 2

    await grandparent.refresh_from_db()
    # The ancestor sees the resolved branch's counts but stays non-authoritative — its other
    # branches were never walked. Descendants: parent + leaf-1 + leaf-2, all selected by the cascade.
    assert grandparent.counts_authoritative is False
    assert grandparent.total_descendant_count == 3
    assert grandparent.selected_descendant_count == 3
