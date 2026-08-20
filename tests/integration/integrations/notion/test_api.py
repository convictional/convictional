from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

from app.models.workspaces.documents import Document
from config.enums import Integration
from infra.jobs import InlineJobs, Job
from integrations.notion.client import (
    NotionAPIError,
    NotionAuthError,
    NotionChildNode,
    NotionChildNodeListPage,
    NotionDatabaseInfo,
    NotionDataSourceQueryPage,
    NotionDataSourceRef,
    NotionNode,
    NotionNodeListPage,
    NotionWorkspaceInfo,
)
from integrations.notion.jobs import CascadeNotionSelectionJob, SyncNotionPagesJob
from integrations.notion.models import NotionConnection, NotionPage
from tests.helpers.app import AppClient
from tests.helpers.factories import create_document, create_notion_connection, create_notion_page


def _node(
    node_id: str = "node-1",
    kind: str = "page",
    title: str = "Title",
    parent_id: str | None = None,
    parent_kind: str | None = "workspace",
    has_children: bool = False,
) -> NotionNode:
    return NotionNode(
        node_id=node_id,
        kind=kind,
        title=title,
        parent_id=parent_id,
        parent_kind=parent_kind,
        last_edited_time=datetime(2026, 1, 1, tzinfo=UTC),
        url=f"https://notion.so/{node_id}",
        has_children=has_children,
    )


def _node_page(nodes: list[NotionNode] | None = None, has_more: bool = False, next_cursor: str | None = None):
    return NotionNodeListPage(nodes=nodes or [], next_cursor=next_cursor, has_more=has_more)


def _child(node_id: str, kind: str = "page", title: str = "Child", has_children: bool = False) -> NotionChildNode:
    return NotionChildNode(node_id=node_id, kind=kind, title=title, has_children=has_children)


def _child_page(nodes: list[NotionChildNode] | None = None, has_more: bool = False, next_cursor: str | None = None):
    return NotionChildNodeListPage(nodes=nodes or [], next_cursor=next_cursor, has_more=has_more)


def _data_source_row(row_id: str, title: str) -> dict:
    return {
        "id": row_id,
        "properties": {"Name": {"type": "title", "title": [{"plain_text": title}]}},
    }


async def _connect(client: AppClient) -> tuple:
    user = await client.get_default_user()
    await user.add_integration(Integration.NOTION)
    connection = await create_notion_connection(user_id=user.id, workspace_name="Acme HQ")
    return user, connection


@pytest.mark.asyncio
async def test_status_reports_connection_and_last_synced_at(client: AppClient):
    response = await client.get("/api/integrations/notion/connection")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"is_connected": False, "workspace_name": None, "last_synced_at": None}

    user, connection = await _connect(client)
    synced_at = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
    await create_notion_page(user_id=user.id, notion_connection_id=connection.id, last_synced_at=synced_at)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        last_synced_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    response = await client.get("/api/integrations/notion/connection")
    body = response.json()
    assert body["is_connected"] is True
    assert body["workspace_name"] == "Acme HQ"
    assert "2026-02-01" in body["last_synced_at"]


@pytest.mark.asyncio
async def test_nodes_list_top_tier_envelope_counts_and_authoritative(client: AppClient):
    user, connection = await _connect(client)
    document = await create_document(organization_id=user.organization_id, creator_id=user.id, title="Imported Doc")
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="page-top",
        kind="page",
        is_selected_for_sync=True,
        document_id=document.id,
    )
    # A database folder with stored counts that are authoritative.
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="db-top",
        kind="database",
        selected_descendant_count=2,
        total_descendant_count=5,
        counts_authoritative=True,
    )

    node_page = _node_page(
        nodes=[
            _node(node_id="page-top", kind="page", title="Planning", parent_kind="workspace"),
            _node(node_id="db-top", kind="database", title="Tasks DB", parent_kind="workspace", has_children=True),
            # A nested page (parent is a page) must be filtered out of the top tier.
            _node(node_id="nested", kind="page", title="Nested", parent_id="page-top", parent_kind="page"),
        ],
        has_more=True,
        next_cursor="cur-2",
    )
    with patch("integrations.notion.api.NotionClient.list_accessible_nodes", AsyncMock(return_value=node_page)):
        response = await client.get("/api/integrations/notion/nodes")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["next_cursor"] == "cur-2"
    assert body["has_more"] is True
    ids = {n["notion_node_id"] for n in body["nodes"]}
    assert ids == {"page-top", "db-top"}

    page_node = next(n for n in body["nodes"] if n["notion_node_id"] == "page-top")
    assert page_node["kind"] == "page"
    assert page_node["is_selected_for_sync"] is True
    assert page_node["is_imported"] is True
    assert page_node["document_id"] == str(document.id)
    assert page_node["url"] == "https://notion.so/page-top"
    assert page_node["counts_authoritative"] is False

    db_node = next(n for n in body["nodes"] if n["notion_node_id"] == "db-top")
    assert db_node["kind"] == "database"
    assert db_node["has_children"] is True
    assert db_node["selected_descendant_count"] == 2
    assert db_node["total_descendant_count"] == 5
    assert db_node["counts_authoritative"] is True
    # Folder rows never report leaf-only selection flags.
    assert db_node["is_selected_for_sync"] is False
    assert db_node["is_imported"] is False


@pytest.mark.asyncio
async def test_nodes_list_forwards_cursor(client: AppClient):
    await _connect(client)
    list_mock = AsyncMock(return_value=_node_page(nodes=[_node(node_id="b", title="Beta")]))
    with patch("integrations.notion.api.NotionClient.list_accessible_nodes", list_mock):
        response = await client.get("/api/integrations/notion/nodes?cursor=cur-2")

    assert response.status_code == status.HTTP_200_OK
    assert list_mock.await_args is not None
    assert list_mock.await_args.kwargs.get("cursor") == "cur-2"


@pytest.mark.asyncio
async def test_nodes_list_error_states(client: AppClient):
    await client.get_default_user()
    response = await client.get("/api/integrations/notion/nodes")
    assert response.status_code == status.HTTP_409_CONFLICT

    await _connect(client)

    with patch(
        "integrations.notion.api.NotionClient.list_accessible_nodes",
        AsyncMock(side_effect=NotionAuthError(401, "unauthorized", "bad token")),
    ):
        response = await client.get("/api/integrations/notion/nodes")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    with patch(
        "integrations.notion.api.NotionClient.list_accessible_nodes",
        AsyncMock(side_effect=NotionAPIError(503, "service_unavailable", "boom")),
    ):
        response = await client.get("/api/integrations/notion/nodes")
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


@pytest.mark.asyncio
async def test_node_children_page_branch_persists_rows_and_counts(client: AppClient):
    user, connection = await _connect(client)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="parent-page",
        kind="page",
    )

    child_page = _child_page(
        nodes=[
            _child("kid-page", kind="page", title="Child Page"),
            _child("kid-db", kind="database", title="Child DB", has_children=True),
        ],
        has_more=True,
        next_cursor="cur-children",
    )
    with patch("integrations.notion.api.NotionClient.list_child_nodes", AsyncMock(return_value=child_page)):
        response = await client.get("/api/integrations/notion/nodes/parent-page/children")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["next_cursor"] == "cur-children"
    assert body["has_more"] is True
    assert {n["notion_node_id"] for n in body["nodes"]} == {"kid-page", "kid-db"}

    # Discovered children are persisted with normalized parent edge + kind.
    kid_page = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="kid-page")
    assert kid_page.kind == "page"
    assert kid_page.parent_notion_id == "parent-page"
    assert kid_page.parent_kind == "page"
    kid_db = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="kid-db")
    assert kid_db.kind == "database"
    assert kid_db.parent_notion_id == "parent-page"

    # Parent counts refreshed from known leaf children (one leaf page child, none selected yet).
    parent = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="parent-page")
    assert parent.total_descendant_count == 1
    assert parent.selected_descendant_count == 0


@pytest.mark.asyncio
async def test_node_children_tolerates_concurrent_child_insert(client: AppClient):
    # Two browser tabs expanding the same parent both read "no row" for a new child (the read is
    # outside the transaction), then both insert. The loser hits the unique constraint on
    # (notion_connection_id, notion_page_id). The handler must absorb it and return the winner's
    # row rather than surfacing an IntegrityError as a 500.
    #
    # Reproduction: the winner's row already exists committed, but we hide it from the handler's
    # initial (pre-transaction) read so the handler still attempts the insert. The insert genuinely
    # violates the constraint mid-transaction, which exercises the savepoint: the failed insert rolls
    # back to the savepoint (not the whole transaction) and the handler refetches the winner's row.
    user, connection = await _connect(client)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="parent-page",
        kind="page",
    )
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="kid-page",
        kind="page",
        title="Winner",
    )

    real_filter = NotionPage.filter

    def hiding_filter(*args, **kwargs):
        # Mimic the racy read that ran before the concurrent winner committed: the new child is absent.
        return real_filter(*args, **kwargs).exclude(notion_page_id="kid-page")

    child_page = _child_page(nodes=[_child("kid-page", kind="page", title="Loser")])
    with (
        patch("integrations.notion.api.NotionClient.list_child_nodes", AsyncMock(return_value=child_page)),
        patch.object(NotionPage, "filter", side_effect=hiding_filter),
    ):
        response = await client.get("/api/integrations/notion/nodes/parent-page/children")

    # No IntegrityError escaped as a 500; the response reflects the persisted (winner's) row.
    assert response.status_code == status.HTTP_200_OK
    assert {n["notion_node_id"] for n in response.json()["nodes"]} == {"kid-page"}
    # Still exactly one row for the key — the losing insert did not create a duplicate.
    assert await NotionPage.filter(notion_connection_id=connection.id, notion_page_id="kid-page").count() == 1
    kid = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="kid-page")
    # The loser refetched the surviving row and applied its normalized parent edge to it.
    assert kid.parent_notion_id == "parent-page"
    assert kid.parent_kind == "page"


@pytest.mark.asyncio
async def test_node_children_database_branch_queries_data_source(client: AppClient):
    user, connection = await _connect(client)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="parent-db",
        kind="database",
    )

    database = NotionDatabaseInfo(
        database_id="parent-db",
        title="Tasks",
        data_sources=[NotionDataSourceRef(data_source_id="ds-1", name="Default")],
    )
    query_page = NotionDataSourceQueryPage(
        rows=[_data_source_row("row-1", "Row One"), _data_source_row("row-2", "Row Two")],
        next_cursor="cur-rows",
        has_more=True,
    )
    get_db = AsyncMock(return_value=database)
    query_ds = AsyncMock(return_value=query_page)
    list_children = AsyncMock(return_value=_child_page())
    with (
        patch("integrations.notion.api.NotionClient.get_database", get_db),
        patch("integrations.notion.api.NotionClient.query_data_source", query_ds),
        patch("integrations.notion.api.NotionClient.list_child_nodes", list_children),
    ):
        response = await client.get("/api/integrations/notion/nodes/parent-db/children")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["next_cursor"] == "cur-rows"
    assert {n["notion_node_id"] for n in body["nodes"]} == {"row-1", "row-2"}
    assert all(n["kind"] == "page" for n in body["nodes"])
    # The database branch must not call the page-children endpoint.
    list_children.assert_not_awaited()
    query_ds.assert_awaited_once()

    # Rows persisted as leaf pages under the database.
    row = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="row-1")
    assert row.kind == "page"
    assert row.parent_notion_id == "parent-db"
    assert row.parent_kind == "database"
    assert row.title == "Row One"


@pytest.mark.asyncio
async def test_node_children_unsaved_top_tier_database_uses_client_kind(client: AppClient):
    # Top-tier nodes aren't persisted until expanded or selected, so a first-expand of a top-tier
    # database has no NotionPage row. The client-supplied kind must drive the database branch;
    # without it the handler would fall back to "page" and call block-children, returning no rows.
    user, connection = await _connect(client)

    database = NotionDatabaseInfo(
        database_id="db-top",
        title="Tasks",
        data_sources=[NotionDataSourceRef(data_source_id="ds-1", name="Default")],
    )
    query_page = NotionDataSourceQueryPage(
        rows=[_data_source_row("row-1", "Row One")], next_cursor=None, has_more=False
    )
    get_db = AsyncMock(return_value=database)
    query_ds = AsyncMock(return_value=query_page)
    list_children = AsyncMock(return_value=_child_page())
    with (
        patch("integrations.notion.api.NotionClient.get_database", get_db),
        patch("integrations.notion.api.NotionClient.query_data_source", query_ds),
        patch("integrations.notion.api.NotionClient.list_child_nodes", list_children),
    ):
        response = await client.get("/api/integrations/notion/nodes/db-top/children?kind=database")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert {n["notion_node_id"] for n in body["nodes"]} == {"row-1"}
    # Database branch taken even though no row was persisted; block-children endpoint untouched.
    query_ds.assert_awaited_once()
    list_children.assert_not_awaited()

    row = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="row-1")
    assert row.parent_notion_id == "db-top"
    assert row.parent_kind == "database"


@pytest.mark.asyncio
async def test_node_children_error_states(client: AppClient):
    await client.get_default_user()
    response = await client.get("/api/integrations/notion/nodes/some-node/children")
    assert response.status_code == status.HTTP_409_CONFLICT

    await _connect(client)
    with patch(
        "integrations.notion.api.NotionClient.list_child_nodes",
        AsyncMock(side_effect=NotionAPIError(502, "bad_gateway", "boom")),
    ):
        response = await client.get("/api/integrations/notion/nodes/some-node/children")
    assert response.status_code == status.HTTP_502_BAD_GATEWAY


@pytest.mark.asyncio
async def test_node_selection_enqueues_cascade_and_returns_202(
    client: AppClient, background_jobs: InlineJobs, monkeypatch
):
    monkeypatch.setattr("integrations.notion.jobs.CascadeNotionSelectionJob.perform", AsyncMock())
    user, connection = await _connect(client)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="db-folder",
        kind="database",
        selected_descendant_count=0,
        total_descendant_count=4,
    )

    response = await client.patch(
        "/api/integrations/notion/nodes/db-folder/selection",
        json={"selected_for_sync": True},
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    body = response.json()
    assert body["notion_node_id"] == "db-folder"
    assert body["kind"] == "database"
    assert body["selected_for_sync"] is True
    assert body["total_descendant_count"] == 4
    assert body["counts_authoritative"] is False

    assert background_jobs.has_completed_job(CascadeNotionSelectionJob)
    queued = background_jobs.find_completed_job_by_type(CascadeNotionSelectionJob)
    assert queued is not None
    assert queued.job_details["node_id"] == "db-folder"
    assert queued.job_details["kind"] == "database"
    assert queued.job_details["selected"] is True
    assert queued.job_details["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_node_selection_error_states(client: AppClient, background_jobs: InlineJobs, monkeypatch):
    monkeypatch.setattr("integrations.notion.jobs.CascadeNotionSelectionJob.perform", AsyncMock())
    user = await client.get_default_user()

    response = await client.patch(
        "/api/integrations/notion/nodes/db-folder/selection", json={"selected_for_sync": True}
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert not background_jobs.has_completed_job(CascadeNotionSelectionJob)

    await user.add_integration(Integration.NOTION)
    await create_notion_connection(user_id=user.id)

    response = await client.patch("/api/integrations/notion/nodes/db-folder/selection", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_selection_state_reports_job_state_and_counts(
    client: AppClient, background_jobs: InlineJobs, monkeypatch
):
    monkeypatch.setattr("integrations.notion.jobs.CascadeNotionSelectionJob.perform", AsyncMock())
    user, connection = await _connect(client)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="db-folder",
        kind="database",
        selected_descendant_count=3,
        total_descendant_count=3,
        counts_authoritative=True,
    )

    # No cascade on record yet → null state, counts still returned from the row.
    response = await client.get("/api/integrations/notion/nodes/db-folder/selection")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["state"] is None
    assert body["node"]["total_descendant_count"] == 3
    assert body["node"]["counts_authoritative"] is True

    # Enqueue + run a cascade inline → the persisted Job row is SUCCESSFUL → "done".
    await client.patch("/api/integrations/notion/nodes/db-folder/selection", json={"selected_for_sync": True})

    response = await client.get("/api/integrations/notion/nodes/db-folder/selection")
    body = response.json()
    assert body["state"] == "done"
    assert body["node"]["notion_node_id"] == "db-folder"


@pytest.mark.asyncio
async def test_selection_state_reports_failed_job(client: AppClient):
    user, connection = await _connect(client)
    await create_notion_page(
        user_id=user.id,
        notion_connection_id=connection.id,
        notion_page_id="db-folder",
        kind="database",
    )
    # A failed cascade Job row (error set, not completed) → "failed".
    await Job.create(
        job_type=CascadeNotionSelectionJob.job_type(),
        job_details={"user_id": str(user.id), "node_id": "db-folder", "kind": "database", "selected": True},
        error="boom",
    )

    response = await client.get("/api/integrations/notion/nodes/db-folder/selection")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["state"] == "failed"


@pytest.mark.asyncio
async def test_selection_state_not_connected_returns_409(client: AppClient):
    await client.get_default_user()
    response = await client.get("/api/integrations/notion/nodes/db-folder/selection")
    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_leaf_page_selection_update_creates_and_updates(client: AppClient):
    user, connection = await _connect(client)

    response = await client.patch(
        "/api/integrations/notion/pages/new-page-id",
        json={
            "selected_for_sync": True,
            "title": "Roadmap",
            "parent_id": "workspace",
            "last_edited_time": "2026-01-01T00:00:00Z",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["notion_page_id"] == "new-page-id"
    assert body["is_selected_for_sync"] is True

    row = await NotionPage.get(notion_connection_id=connection.id, notion_page_id="new-page-id")
    assert row.is_selected_for_sync is True
    assert row.title == "Roadmap"

    response = await client.patch(
        "/api/integrations/notion/pages/new-page-id",
        json={"selected_for_sync": False},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_selected_for_sync"] is False


@pytest.mark.asyncio
async def test_connection_create_and_refresh(client: AppClient):
    user = await client.get_default_user()
    workspace = NotionWorkspaceInfo(bot_id="bot-1", workspace_id="ws-1", workspace_name="Acme")
    with patch("integrations.notion.api.NotionClient.validate_token", AsyncMock(return_value=workspace)):
        created = await client.post("/api/integrations/notion/connection", json={"access_token": "secret_valid_token"})
    assert created.status_code == status.HTTP_201_CREATED
    assert created.json() == {"is_connected": True, "workspace_name": "Acme"}

    stored = await NotionConnection.get(user_id=user.id)
    assert stored.access_token == "secret_valid_token"

    refreshed_workspace = NotionWorkspaceInfo(bot_id="bot-2", workspace_id="ws-2", workspace_name="Acme Renamed")
    with patch("integrations.notion.api.NotionClient.validate_token", AsyncMock(return_value=refreshed_workspace)):
        refreshed = await client.post("/api/integrations/notion/connection", json={"access_token": "secret_new_token"})
    assert refreshed.status_code == status.HTTP_200_OK
    assert await NotionConnection.filter(user_id=user.id).count() == 1


@pytest.mark.asyncio
async def test_connection_delete_removes_connection_and_pages(client: AppClient):
    user, connection = await _connect(client)
    document = await create_document(organization_id=user.organization_id, creator_id=user.id, title="Imported Doc")
    await create_notion_page(user_id=user.id, notion_connection_id=connection.id, is_selected_for_sync=True)
    await create_notion_page(
        user_id=user.id, notion_connection_id=connection.id, document_id=document.id, is_selected_for_sync=True
    )

    response = await client.delete("/api/integrations/notion/connection")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""

    assert await NotionConnection.get_or_none(user_id=user.id) is None
    assert await NotionPage.filter(user_id=user.id).count() == 0
    assert await Document.get_or_none(id=document.id) is not None


@pytest.mark.asyncio
async def test_sync_enqueues_job(client: AppClient, background_jobs: InlineJobs, monkeypatch):
    monkeypatch.setattr("integrations.notion.jobs.SyncNotionPagesJob.perform", AsyncMock())
    user, connection = await _connect(client)
    synced_at = datetime(2026, 3, 1, tzinfo=UTC)
    await create_notion_page(user_id=user.id, notion_connection_id=connection.id, last_synced_at=synced_at)

    response = await client.post("/api/integrations/notion/sync")
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert "2026-03-01" in response.json()["last_synced_at"]

    assert background_jobs.has_completed_job(SyncNotionPagesJob)
    queued = background_jobs.find_completed_job_by_type(SyncNotionPagesJob)
    assert queued is not None
    assert queued.job_details["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_sync_without_connection_returns_409_and_does_not_enqueue(
    client: AppClient, background_jobs: InlineJobs, monkeypatch
):
    monkeypatch.setattr("integrations.notion.jobs.SyncNotionPagesJob.perform", AsyncMock())
    await client.get_default_user()

    response = await client.post("/api/integrations/notion/sync")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert not background_jobs.has_completed_job(SyncNotionPagesJob)


@pytest.mark.asyncio
async def test_endpoints_require_auth(client: AppClient):
    with client.logged_out():
        status_response = await client.get("/api/integrations/notion/connection")
        nodes_response = await client.get("/api/integrations/notion/nodes")
        children_response = await client.get("/api/integrations/notion/nodes/node-1/children")
        selection_get_response = await client.get("/api/integrations/notion/nodes/node-1/selection")
        cascade_response = await client.patch(
            "/api/integrations/notion/nodes/node-1/selection", json={"selected_for_sync": True}
        )
        create_response = await client.post("/api/integrations/notion/connection", json={"access_token": "secret"})
        delete_response = await client.delete("/api/integrations/notion/connection")
        patch_response = await client.patch("/api/integrations/notion/pages/page-1", json={"selected_for_sync": True})
        sync_response = await client.post("/api/integrations/notion/sync")

    for response in (
        status_response,
        nodes_response,
        children_response,
        selection_get_response,
        cascade_response,
        create_response,
        delete_response,
        patch_response,
        sync_response,
    ):
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
