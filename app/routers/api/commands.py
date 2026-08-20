from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from app.helpers.url import url_for_content
from app.helpers.users import user_avatar_url
from app.models.accounts import User
from app.models.collaboration.content import (
    ContentLookupQuery,
    LookupSearchMetric,
    RecentAuthorActivity,
    run_lookup_search,
)
from app.models.collaboration.workspace import Visit, WorkspaceResourceFetcher
from app.models.commands import SYSTEM_COMMANDS, Command, QuickLink
from app.models.workspaces.chat import Chat
from app.models.workspaces.email.contact import EmailContact
from app.presenters.lookup_results import LookupResultPresenter, LookupResultsPresenter
from app.routers.api.schemas import PaginatedResponse
from app.routers.dependencies import get_current_user
from infra.db import GlobalID, RecordModel

router = APIRouter(tags=["commands"])


@dataclass
class AuthorFilter:
    authors_like: list[str]
    filter_user: User | None = None
    filter_contact: EmailContact | None = None


def build_author_filter(entity: RecordModel | None, current_user: User) -> AuthorFilter | None:
    if not entity:
        return None

    if isinstance(entity, User):
        if entity.organization_id != current_user.organization_id:
            return None
        return AuthorFilter(
            authors_like=[entity.email, entity.display_name],
            filter_user=entity,
        )
    elif isinstance(entity, EmailContact):
        if entity.organization_id != current_user.organization_id or entity.user_id != current_user.id:
            return None
        return AuthorFilter(
            authors_like=[entity.email],
            filter_contact=entity,
        )
    else:
        return None


async def get_commands(current_user: User = Depends(get_current_user)):
    quick_links = await QuickLink.filter(QuickLink.filters.by_owner(current_user.id))
    all_commands = SYSTEM_COMMANDS + [cmd.as_command for cmd in quick_links]
    return sorted(all_commands, key=lambda c: c.label.lower())


class CommandResponse(BaseModel):
    key: str
    type: str
    label: str
    description: str | None
    url: str | None
    options: dict | None
    quick_link_id: str | None


class CommandsListResponse(PaginatedResponse):
    commands: list[CommandResponse]


class CollaboratorResponse(BaseModel):
    id: str
    display_name: str


class RecentItemResponse(BaseModel):
    workspace_id: str
    resource_type: str
    title: str
    url: str
    updated_at: datetime
    collaborators: list[CollaboratorResponse]
    preview: str | None


class RecentResponse(PaginatedResponse):
    recent_items: list[RecentItemResponse]


class LookupResultResponse(BaseModel):
    id: str
    content_type: str
    title: str
    url: str
    updated_at: datetime
    display_at: datetime
    authors: list[str]
    preview: str | None
    shared_with_me: bool
    email: str | None
    avatar_url: str | None
    global_id: str


class LookupResultsResponse(BaseModel):
    user_results: list[LookupResultResponse]
    other_results: list[LookupResultResponse]


class FilterMetaResponse(BaseModel):
    kind: str
    id: str
    name: str
    email: str | None
    avatar_url: str | None
    global_id: str


class LookupResponse(BaseModel):
    results: LookupResultsResponse
    query: str


class PeopleResponse(BaseModel):
    results: LookupResultsResponse
    query: str
    filter: FilterMetaResponse | None


class LookupTrackRequest(BaseModel):
    query: str = Field(max_length=500)
    result_count: int = Field(ge=0, le=10_000)
    result_ids: list[UUID] = Field(max_length=100)
    clicked_content_id: UUID | None = None
    clicked_position: int | None = Field(default=None, ge=0, le=10_000)
    filter_author_gid: str | None = Field(default=None, max_length=200)


MAX_RECENT_ITEMS = 5
MIN_QUERY_LENGTH = 2


def _command_response(command: Command) -> CommandResponse:
    return CommandResponse(
        key=command.key,
        type=command.type.value,
        label=command.label,
        description=command.description,
        url=command.url,
        options=command.options,
        quick_link_id=command.key if command.type.is_quick_link else None,
    )


def _lookup_result_response(
    presenter: LookupResultPresenter, request: Request, current_user: User
) -> LookupResultResponse:
    result = presenter.model
    return LookupResultResponse(
        id=str(result.id),
        content_type=result.content_type.value,
        title=result.title,
        url=url_for_content(request, result),
        updated_at=result.updated_at,
        display_at=presenter.display_at,
        authors=[a.strip() for a in (result.author or "").split(",") if a.strip()],
        preview=presenter.preview,
        shared_with_me=presenter.shared_with_me(current_user),
        email=presenter.email,
        avatar_url=presenter.avatar_url,
        global_id=str(result.source_global_id),
    )


def _lookup_results_response(
    results: LookupResultsPresenter, request: Request, current_user: User
) -> LookupResultsResponse:
    return LookupResultsResponse(
        user_results=[_lookup_result_response(p, request, current_user) for p in results.user_results],
        other_results=[_lookup_result_response(p, request, current_user) for p in results.other_results],
    )


@router.get("/commands", response_model=CommandsListResponse)
async def api_commands(commands: list[Command] = Depends(get_commands)):
    return CommandsListResponse(
        commands=[_command_response(c) for c in commands],
    )


@router.get("/commands/recent", response_model=RecentResponse)
async def api_commands_recent(request: Request, current_user: User = Depends(get_current_user)):
    # Reads Visit rows directly (not ViewStateResolver): this is a recency-ordered listing of the
    # user's most recent visits joined to their workspaces/resources for rendering — a different
    # query shape than the resolver's per-known-workspace view-state lookup.
    recent_visits = (
        await Visit.filter(Visit.filters.by_user(current_user.id))
        .limit(MAX_RECENT_ITEMS)
        .prefetch_related("workspace__collaborators__user")
    )
    await WorkspaceResourceFetcher(
        workspaces=[v.workspace for v in recent_visits],
        prefetch_map={Chat: ["last_message__user"]},
    ).fetch()
    visible_visits = [v for v in recent_visits if v.workspace.is_resource_fetched]

    recent_items = []
    for visit in visible_visits:
        workspace = visit.workspace
        resource = workspace.resource
        if isinstance(resource, Chat):
            title = resource.resolved_title(viewer_id=None)
            preview = resource.last_message_preview(max_length=200)
        else:
            title = resource.title
            preview = None
        recent_items.append(
            RecentItemResponse(
                workspace_id=str(workspace.id),
                resource_type=workspace.resource_type,
                title=title,
                url=str(request.url_for("gid_redirect", gid=resource.global_id.to_param)),
                updated_at=visit.updated_at,
                collaborators=[
                    CollaboratorResponse(id=str(c.user.id), display_name=c.user.display_name)
                    for c in workspace.collaborators
                    if c.user
                ],
                preview=preview,
            )
        )
    return RecentResponse(recent_items=recent_items)


@router.get("/commands/lookup", response_model=LookupResponse)
async def api_commands_lookup(
    request: Request,
    query: str = Query(""),
    current_user: User = Depends(get_current_user),
):
    if len(query.strip()) < MIN_QUERY_LENGTH:
        empty = await LookupResultsPresenter.create([], current_user=current_user)
        return LookupResponse(results=_lookup_results_response(empty, request, current_user), query=query)

    content_results, _ = await run_lookup_search(
        organization=current_user.organization,
        query=query,
        user=current_user,
    )
    results = await LookupResultsPresenter.create(content_results, current_user=current_user)
    return LookupResponse(results=_lookup_results_response(results, request, current_user), query=query)


@router.get("/commands/people", response_model=PeopleResponse)
async def api_commands_people(
    request: Request,
    author_gid: str = Query(...),
    query: str = Query(""),
    current_user: User = Depends(get_current_user),
):
    parsed_gid = GlobalID.parse(author_gid)
    entity = await parsed_gid.get_or_none()
    if isinstance(entity, User):
        entity = await User.get(id=entity.id).select_related("avatar_file")

    author_filter = build_author_filter(entity, current_user)
    if not author_filter:
        empty = await LookupResultsPresenter.create([], current_user=current_user)
        return PeopleResponse(results=_lookup_results_response(empty, request, current_user), query=query, filter=None)

    if query.strip():
        content_lookup = ContentLookupQuery(
            organization=current_user.organization,
            query=query,
            current_user=current_user,
            authors_like=author_filter.authors_like,
        )
        content_results = await content_lookup.execute()
    else:
        recent_activity = RecentAuthorActivity(
            organization=current_user.organization,
            authors_like=author_filter.authors_like,
            current_user=current_user,
        )
        content_results = await recent_activity.execute()

    results = await LookupResultsPresenter.create(content_results, current_user=current_user)

    filter_meta: FilterMetaResponse | None = None
    if author_filter.filter_user:
        u = author_filter.filter_user
        filter_meta = FilterMetaResponse(
            kind="user",
            id=str(u.id),
            name=u.display_name,
            email=u.email,
            avatar_url=user_avatar_url(u),
            global_id=str(u.global_id),
        )
    elif author_filter.filter_contact:
        c = author_filter.filter_contact
        filter_meta = FilterMetaResponse(
            kind="contact",
            id=str(c.id),
            name=c.name or c.email,
            email=c.email,
            avatar_url=None,
            global_id=str(c.global_id),
        )

    return PeopleResponse(
        results=_lookup_results_response(results, request, current_user),
        query=query,
        filter=filter_meta,
    )


@router.post("/commands/lookup/track", status_code=status.HTTP_204_NO_CONTENT)
async def api_commands_lookup_track(
    payload: LookupTrackRequest,
    current_user: User = Depends(get_current_user),
):
    await LookupSearchMetric.create(
        query=payload.query,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        result_count=payload.result_count,
        result_ids=[str(rid) for rid in payload.result_ids],
        clicked_content_id=payload.clicked_content_id,
        clicked_position=payload.clicked_position,
        filter_author_gid=payload.filter_author_gid,
    )
