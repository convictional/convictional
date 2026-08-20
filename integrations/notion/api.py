"""
JSON API endpoints for the Notion integration, consumed by the React island.

Lives in `integrations/notion/` because the handlers reach `NotionClient`,
`NotionConnection`, `NotionPage`, and `SyncNotionPagesJob`, and the .importlinter
contract forbids `app -> integrations`. Mounted under `/api/...` from
`app/main.py` (mirroring `integrations/recall_ai/api.py`).

The browser HTML flow stays in `router.py`; this module is the React-facing
JSON contract for the same logic.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from tortoise.exceptions import IntegrityError
from tortoise.functions import Max
from tortoise.transactions import in_transaction

from app.models.accounts import User
from app.routers.api.schemas import PaginatedResponse
from app.routers.dependencies import get_current_user
from config import logger
from config.enums import Integration, JobStatus
from infra.db import transaction
from infra.jobs import Job, enqueue_job
from integrations.notion.client import (
    NotionAPIError,
    NotionAuthError,
    NotionChildNode,
    NotionClient,
)
from integrations.notion.enums import NotionNodeKind
from integrations.notion.jobs import CascadeNotionSelectionJob, SyncNotionPagesJob, row_title
from integrations.notion.models import NotionConnection, NotionPage

router = APIRouter(tags=["notion integration"])

NOTION_TOKEN_INVALID_DETAIL = "Your Notion token is no longer valid. Please reconnect Notion."
NOTION_UNREACHABLE_DETAIL = "Couldn't reach Notion right now. Please try again."
NOTION_NOT_CONNECTED_DETAIL = "Connect Notion before performing this action."

CASCADE_JOB_TYPE = CascadeNotionSelectionJob.job_type()

# Top-tier nodes are those whose parent is the workspace itself (or unknown).
TOP_TIER_PARENT_KINDS: frozenset[str | None] = frozenset((None, "workspace"))

_JOB_STATUS_TO_SELECTION_STATE: dict[JobStatus, str] = {
    JobStatus.SCHEDULED: "pending",
    JobStatus.ENQUEUED: "pending",
    JobStatus.STARTED: "running",
    JobStatus.SUCCESSFUL: "done",
    JobStatus.FAILED: "failed",
    JobStatus.TERMINATED: "failed",
    JobStatus.DEAD: "failed",
}


#
# Response & request models
#


class NotionConnectionResponse(BaseModel):
    is_connected: bool
    workspace_name: str | None


class NotionStatusResponse(BaseModel):
    is_connected: bool
    workspace_name: str | None
    last_synced_at: datetime | None


class NotionSyncStatusResponse(BaseModel):
    last_synced_at: datetime | None


class NotionPageResponse(BaseModel):
    notion_page_id: str
    title: str
    parent_id: str | None
    last_edited_time: datetime | None
    url: str | None
    is_selected_for_sync: bool
    is_imported: bool
    # String UUID of the imported Convictional Document, or null. The island
    # builds the document URL itself — the API returns the identifier only.
    document_id: str | None


class NotionNodeResponse(BaseModel):
    notion_node_id: str
    kind: str  # "page" | "database"
    title: str
    parent_id: str | None
    parent_kind: str | None  # "page" | "database" | "workspace" | None
    has_children: bool
    url: str | None
    last_edited_time: datetime | None
    # Leaf pages only — folder (database) rows are never flagged for sync.
    is_selected_for_sync: bool
    is_imported: bool
    # String UUID of the imported Convictional Document (leaf pages only), or null.
    document_id: str | None
    # Denormalized, folder-only counts read straight off the stored columns.
    selected_descendant_count: int
    total_descendant_count: int
    # False until a subtree has been resolved (cascade) or expanded; the UI renders a
    # neutral tri-state until this is true.
    counts_authoritative: bool


class NotionNodeListResponse(PaginatedResponse):
    nodes: list[NotionNodeResponse]


class NotionNodeSelectionUpdateRequest(BaseModel):
    # Required (no default) so a body with no recognized fields returns 422. Explicit
    # state (not a toggle): the value is the desired post-cascade selection.
    selected_for_sync: bool
    # The node's kind as the client knows it (from the nodes API). The cascade job needs it to
    # pick page- vs database-traversal, and a top-tier node isn't persisted until it's expanded or
    # selected — so the DB can't always tell us. The client is the reliable source.
    kind: str | None = None


class NotionNodeSelectionAcceptedResponse(BaseModel):
    # Echoed back so the UI can seed its optimistic flip; counts may still be
    # non-authoritative until the enqueued cascade resolves the subtree.
    notion_node_id: str
    kind: str
    selected_for_sync: bool
    selected_descendant_count: int
    total_descendant_count: int
    counts_authoritative: bool


class NotionSelectionNodeState(BaseModel):
    notion_node_id: str
    selected_descendant_count: int
    total_descendant_count: int
    counts_authoritative: bool


class NotionSelectionStateResponse(BaseModel):
    # "pending" | "running" | "done" | "failed" — null when no cascade is on record.
    state: str | None
    node: NotionSelectionNodeState | None


class NotionConnectionCreateRequest(BaseModel):
    access_token: str = Field(min_length=1)

    @field_validator("access_token")
    @classmethod
    def token_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("access_token must not be blank")
        return stripped


class NotionPageSelectionUpdateRequest(BaseModel):
    # Required (no default) so a body with no recognized fields returns 422.
    selected_for_sync: bool
    # Placeholder metadata used to seed/refresh the NotionPage row so the next
    # render reflects current values without waiting for a sync.
    title: str | None = None
    parent_id: str | None = None
    last_edited_time: datetime | None = None


#
# Helpers
#


async def _require_connection(current_user: User) -> NotionConnection:
    connection = await NotionConnection.get_or_none(user_id=current_user.id)
    # 409: the request is well-formed but the account has no Notion connection
    # yet — a state conflict the caller resolves by connecting first.
    if connection is None or not current_user.is_integrated_with(Integration.NOTION):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NOTION_NOT_CONNECTED_DETAIL)
    return connection


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def _max_synced_at(connection: NotionConnection) -> datetime | None:
    rows = (
        await NotionPage.filter(notion_connection_id=connection.id)
        .annotate(max_synced_at=Max("last_synced_at"))
        .values("max_synced_at")
    )
    return rows[0]["max_synced_at"] if rows else None


def _page_response(
    *,
    notion_page_id: str,
    title: str | None,
    parent_id: str | None,
    last_edited_time: datetime | None,
    url: str | None,
    saved_page: NotionPage | None,
) -> NotionPageResponse:
    is_imported = saved_page is not None and saved_page.document_id is not None
    return NotionPageResponse(
        notion_page_id=notion_page_id,
        title=title or "(Untitled)",
        parent_id=parent_id,
        last_edited_time=last_edited_time,
        url=url,
        is_selected_for_sync=bool(saved_page and saved_page.is_selected_for_sync),
        is_imported=is_imported,
        document_id=str(saved_page.document_id) if is_imported and saved_page is not None else None,
    )


def _node_response(
    *,
    notion_node_id: str,
    kind: str,
    title: str | None,
    parent_id: str | None,
    parent_kind: str | None,
    has_children: bool,
    url: str | None,
    last_edited_time: datetime | None,
    saved_page: NotionPage | None,
) -> NotionNodeResponse:
    is_leaf_page = kind == NotionNodeKind.PAGE.value
    is_imported = is_leaf_page and saved_page is not None and saved_page.document_id is not None
    return NotionNodeResponse(
        notion_node_id=notion_node_id,
        kind=kind,
        title=title or "(Untitled)",
        parent_id=parent_id,
        parent_kind=parent_kind,
        has_children=has_children,
        url=url,
        last_edited_time=last_edited_time,
        is_selected_for_sync=bool(is_leaf_page and saved_page and saved_page.is_selected_for_sync),
        is_imported=is_imported,
        document_id=str(saved_page.document_id) if is_imported and saved_page is not None else None,
        selected_descendant_count=saved_page.selected_descendant_count if saved_page is not None else 0,
        total_descendant_count=saved_page.total_descendant_count if saved_page is not None else 0,
        counts_authoritative=bool(saved_page and saved_page.counts_authoritative),
    )


async def _saved_pages_by_id(connection: NotionConnection) -> dict[str, NotionPage]:
    saved = await NotionPage.filter(notion_connection_id=connection.id)
    return {page.notion_page_id: page for page in saved}


def _map_notion_error(action: str, exc: NotionAPIError) -> HTTPException:
    if isinstance(exc, NotionAuthError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=NOTION_TOKEN_INVALID_DETAIL)
    logger.exception(f"Notion API error while {action}")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=NOTION_UNREACHABLE_DETAIL)


async def _persist_child_nodes(
    *,
    connection: NotionConnection,
    user_id: UUID,
    parent_id: str,
    parent_kind: str,
    children: list[NotionChildNode],
) -> dict[str, NotionPage]:
    """Upsert discovered children with normalized parent edges, then refresh the parent's counts.

    Returns the saved rows for the parent + children keyed by node id so the caller can build
    responses without re-querying.
    """
    node_ids = [parent_id, *[child.node_id for child in children]]
    existing = await NotionPage.filter(notion_connection_id=connection.id, notion_page_id__in=node_ids)
    by_id = {page.notion_page_id: page for page in existing}

    async def update_existing(row: NotionPage, child: NotionChildNode) -> None:
        row.kind = NotionNodeKind(child.kind)
        row.parent_notion_id = parent_id
        row.parent_kind = parent_kind
        if child.title:
            row.title = child.title
        await row.save(using_db=db)

    async with transaction() as db:
        for child in children:
            row = by_id.get(child.node_id)
            if row is not None:
                await update_existing(row, child)
                continue

            try:
                # A savepoint isolates the insert so a concurrent expansion that already created
                # the same (notion_connection_id, notion_page_id) row only rolls back this insert,
                # not the whole transaction. The unique constraint is the source of truth; the loser
                # of the race refetches the winner's row and applies the same update.
                async with in_transaction("default"):
                    row = await NotionPage.create(
                        user_id=user_id,
                        notion_connection_id=connection.id,
                        notion_page_id=child.node_id,
                        title=child.title or None,
                        kind=child.kind,
                        parent_notion_id=parent_id,
                        parent_kind=parent_kind,
                        using_db=db,
                    )
            except IntegrityError:
                row = await NotionPage.get(
                    notion_connection_id=connection.id, notion_page_id=child.node_id, using_db=db
                )
                await update_existing(row, child)
            by_id[child.node_id] = row

        parent_row = by_id.get(parent_id)
        if parent_row is not None:
            await NotionPage.refresh_parent_leaf_counts(
                notion_connection_id=connection.id, parent=parent_row, using_db=db
            )

    return by_id


async def _latest_cascade_job(connection_user_id: UUID, node_id: str) -> Job | None:
    # The cascade store is just the Job table. A select-job and a deselect-job for the same node are
    # distinct rows (job_details differ on `selected`), so we match on job_type + node_id + user and
    # take the most recent regardless of direction. user_id is filtered in the query (not in Python)
    # so the latest matching job is never missed behind a window of other users' jobs on the same node.
    # job_details__filter takes a single key/value pair, so chain two filters (they AND together).
    return (
        await Job.filter(job_type=CASCADE_JOB_TYPE, job_details__filter={"node_id": node_id})
        .filter(job_details__filter={"user_id": str(connection_user_id)})
        .order_by("-created_at")
        .first()
    )


#
# Endpoints
#


@router.get("/integrations/notion/connection", response_model=NotionStatusResponse)
async def api_notion_connection_get(
    current_user: User = Depends(get_current_user),
) -> NotionStatusResponse:
    connection = await NotionConnection.get_or_none(user_id=current_user.id)
    is_connected = current_user.is_integrated_with(Integration.NOTION) and connection is not None
    return NotionStatusResponse(
        is_connected=is_connected,
        workspace_name=connection.workspace_name if connection is not None else None,
        last_synced_at=await _max_synced_at(connection) if is_connected and connection is not None else None,
    )


@router.get("/integrations/notion/nodes", response_model=NotionNodeListResponse)
async def api_notion_nodes_list(
    cursor: str | None = None,
    current_user: User = Depends(get_current_user),
) -> NotionNodeListResponse:
    connection = await _require_connection(current_user)
    saved = await _saved_pages_by_id(connection)

    async with NotionClient(connection.access_token) as client:
        try:
            page = await client.list_accessible_nodes(cursor=cursor)
        except NotionAPIError as exc:
            raise _map_notion_error("listing nodes", exc)

    nodes = [
        _node_response(
            notion_node_id=node.node_id,
            kind=node.kind,
            title=node.title,
            parent_id=node.parent_id,
            parent_kind=node.parent_kind,
            has_children=node.has_children,
            url=node.url,
            last_edited_time=node.last_edited_time,
            saved_page=saved.get(node.node_id),
        )
        for node in page.nodes
        if node.parent_kind in TOP_TIER_PARENT_KINDS
    ]
    return NotionNodeListResponse(nodes=nodes, next_cursor=page.next_cursor, has_more=page.has_more)


@router.get("/integrations/notion/nodes/{node_id}/children", response_model=NotionNodeListResponse)
async def api_notion_node_children(
    node_id: str,
    cursor: str | None = None,
    kind: str | None = None,
    current_user: User = Depends(get_current_user),
) -> NotionNodeListResponse:
    connection = await _require_connection(current_user)

    # The node's kind decides how its children are fetched (database rows vs. block children).
    saved_parent = await NotionPage.get_or_none(notion_connection_id=connection.id, notion_page_id=node_id)
    parent_kind = NotionPage.effective_kind(kind, saved_parent)

    async with NotionClient(connection.access_token) as client:
        try:
            if parent_kind == NotionNodeKind.DATABASE.value:
                children, next_cursor, has_more = await _database_children(client, node_id, cursor)
            else:
                child_page = await client.list_child_nodes(node_id, cursor=cursor)
                children, next_cursor, has_more = child_page.nodes, child_page.next_cursor, child_page.has_more
        except NotionAPIError as exc:
            raise _map_notion_error("listing node children", exc)

    by_id = await _persist_child_nodes(
        connection=connection,
        user_id=current_user.id,
        parent_id=node_id,
        parent_kind=parent_kind,
        children=children,
    )

    nodes = [
        _node_response(
            notion_node_id=child.node_id,
            kind=child.kind,
            title=child.title,
            parent_id=node_id,
            parent_kind=parent_kind,
            has_children=child.has_children,
            url=None,
            last_edited_time=None,
            saved_page=by_id.get(child.node_id),
        )
        for child in children
    ]
    return NotionNodeListResponse(nodes=nodes, next_cursor=next_cursor, has_more=has_more)


async def _database_children(
    client: NotionClient, database_id: str, cursor: str | None
) -> tuple[list[NotionChildNode], str | None, bool]:
    # A database's children are the rows of each of its data sources. The first data source carries
    # the cursor pagination; multi-data-source databases are rare and walked fully by the cascade.
    database = await client.get_database(database_id)
    if not database.data_sources:
        return [], None, False
    query_page = await client.query_data_source(database.data_sources[0].data_source_id, cursor=cursor)
    children: list[NotionChildNode] = []
    for row in query_page.rows:
        row_id = row.get("id")
        if not isinstance(row_id, str):
            continue
        children.append(
            NotionChildNode(
                node_id=row_id,
                kind=NotionNodeKind.PAGE.value,
                title=row_title(row) or "",
                has_children=bool(row.get("has_children")),
            )
        )
    return children, query_page.next_cursor, query_page.has_more


@router.post(
    "/integrations/notion/connection",
    response_model=NotionConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_notion_connection_create(
    body: NotionConnectionCreateRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> NotionConnectionResponse:
    async with NotionClient(body.access_token) as client:
        try:
            workspace_info = await client.validate_token()
        except NotionAuthError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=NOTION_TOKEN_INVALID_DETAIL)
        except NotionAPIError:
            logger.exception("Notion API error while validating token")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=NOTION_UNREACHABLE_DETAIL)

    async with transaction() as db:
        existing = await NotionConnection.get_or_none(user_id=current_user.id, using_db=db)
        if existing is not None:
            existing.access_token = body.access_token
            existing.workspace_id = workspace_info.workspace_id
            existing.workspace_name = workspace_info.workspace_name
            existing.bot_id = workspace_info.bot_id
            await existing.save(using_db=db)
            workspace_name = existing.workspace_name
        else:
            created = await NotionConnection.create(
                user_id=current_user.id,
                access_token=body.access_token,
                workspace_id=workspace_info.workspace_id,
                workspace_name=workspace_info.workspace_name,
                bot_id=workspace_info.bot_id,
                using_db=db,
            )
            workspace_name = created.workspace_name

        if not current_user.is_integrated_with(Integration.NOTION):
            await current_user.add_integration(Integration.NOTION, using_db=db)

    # 200 when refreshing an existing connection, 201 (route default) when newly created.
    if existing is not None:
        response.status_code = status.HTTP_200_OK
    return NotionConnectionResponse(is_connected=True, workspace_name=workspace_name)


@router.delete("/integrations/notion/connection", status_code=status.HTTP_204_NO_CONTENT)
async def api_notion_connection_delete(
    current_user: User = Depends(get_current_user),
) -> Response:
    async with transaction() as db:
        # Cascade on the FK drops NotionPages; clearing the connection also clears selections.
        await NotionConnection.filter(user_id=current_user.id).using_db(db).delete()
        if current_user.is_integrated_with(Integration.NOTION):
            await current_user.remove_integration(Integration.NOTION, using_db=db)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/integrations/notion/pages/{notion_page_id}", response_model=NotionPageResponse)
async def api_notion_page_selection_update(
    notion_page_id: str,
    body: NotionPageSelectionUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> NotionPageResponse:
    connection = await _require_connection(current_user)
    last_edited_dt = _normalize_datetime(body.last_edited_time)

    async with transaction() as db:
        existing = await NotionPage.get_or_none(
            notion_connection_id=connection.id,
            notion_page_id=notion_page_id,
            using_db=db,
        )
        if existing is None:
            existing = await NotionPage.create(
                user_id=current_user.id,
                notion_connection_id=connection.id,
                notion_page_id=notion_page_id,
                title=body.title or None,
                parent_notion_id=body.parent_id or None,
                notion_last_edited_time=last_edited_dt,
                is_selected_for_sync=body.selected_for_sync,
                using_db=db,
            )
        else:
            existing.is_selected_for_sync = body.selected_for_sync
            if body.title:
                existing.title = body.title
            if body.parent_id:
                existing.parent_notion_id = body.parent_id
            if last_edited_dt is not None:
                existing.notion_last_edited_time = last_edited_dt
            await existing.save(using_db=db)

    return _page_response(
        notion_page_id=existing.notion_page_id,
        title=existing.title,
        parent_id=existing.parent_notion_id,
        last_edited_time=existing.notion_last_edited_time,
        url=None,
        saved_page=existing,
    )


@router.patch(
    "/integrations/notion/nodes/{node_id}/selection",
    response_model=NotionNodeSelectionAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def api_notion_node_selection_update(
    node_id: str,
    body: NotionNodeSelectionUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> NotionNodeSelectionAcceptedResponse:
    # Folder (subtree) selection. Resolving the subtree hits Notion recursively under a 3 RPS
    # budget, so it runs as a job; we accept the request (202) and the UI polls GET /selection to
    # reconcile its optimistic flip. A single-leaf select stays on PATCH /pages/{id}.
    connection = await _require_connection(current_user)

    saved = await NotionPage.get_or_none(notion_connection_id=connection.id, notion_page_id=node_id)
    kind = NotionPage.effective_kind(body.kind, saved)

    await enqueue_job(
        CascadeNotionSelectionJob(
            user_id=current_user.id,
            node_id=node_id,
            kind=kind,
            selected=body.selected_for_sync,
        )
    )

    # Re-read so counts reflect any synchronous (inline-runner) cascade; they may still be
    # non-authoritative under a real queue.
    saved = await NotionPage.get_or_none(notion_connection_id=connection.id, notion_page_id=node_id)
    return NotionNodeSelectionAcceptedResponse(
        notion_node_id=node_id,
        kind=kind,
        selected_for_sync=body.selected_for_sync,
        selected_descendant_count=saved.selected_descendant_count if saved is not None else 0,
        total_descendant_count=saved.total_descendant_count if saved is not None else 0,
        counts_authoritative=bool(saved and saved.counts_authoritative),
    )


@router.get("/integrations/notion/nodes/{node_id}/selection", response_model=NotionSelectionStateResponse)
async def api_notion_selection_state(
    node_id: str,
    current_user: User = Depends(get_current_user),
) -> NotionSelectionStateResponse:
    # Polled by the UI to reconcile an optimistic folder flip: reports the latest cascade job's
    # coarse state plus the node's refreshed (authoritative once done) counts.
    connection = await _require_connection(current_user)

    job = await _latest_cascade_job(connection.user_id, node_id)
    state = _JOB_STATUS_TO_SELECTION_STATE.get(job.status) if job is not None else None

    saved = await NotionPage.get_or_none(notion_connection_id=connection.id, notion_page_id=node_id)
    node = (
        NotionSelectionNodeState(
            notion_node_id=node_id,
            selected_descendant_count=saved.selected_descendant_count,
            total_descendant_count=saved.total_descendant_count,
            counts_authoritative=saved.counts_authoritative,
        )
        if saved is not None
        else None
    )
    return NotionSelectionStateResponse(state=state, node=node)


@router.post(
    "/integrations/notion/sync",
    response_model=NotionSyncStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def api_notion_sync(
    current_user: User = Depends(get_current_user),
) -> NotionSyncStatusResponse:
    connection = await _require_connection(current_user)
    await enqueue_job(SyncNotionPagesJob(user_id=current_user.id))
    return NotionSyncStatusResponse(last_synced_at=await _max_synced_at(connection))
