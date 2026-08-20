import json
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import AwareDatetime, BaseModel, Field, field_validator
from starlette.datastructures import URL
from tortoise.exceptions import DoesNotExist

from app.helpers.email import format_sender_display
from app.helpers.strings import html_to_plain_text
from app.helpers.users import user_avatar_url
from app.models.accounts import User
from app.models.collaboration.mailbox import (
    Mailbox,
    MailboxEntry,
    MailboxViewCache,
    MailboxViewIdentifier,
    MailboxViewSource,
)
from app.models.workspaces.chat import Chat
from app.models.workspaces.email.thread import EmailThread
from app.models.workspaces.goals import Goal
from app.models.workspaces.posts import Post
from app.presenters.mailbox_entries import MailboxEntryPresenter
from app.routers.api.mailbox_views import MAILBOX_VIEW_MAX_ENTRIES
from app.routers.api.schemas import MailboxEntryBase, PaginatedResponse
from app.routers.dependencies import Channel, Helpers, get_current_user, get_helpers, get_mailbox, handle_stream
from config.enums import ChannelEventAction, ChannelEventResource, MailboxSort, MailboxViewName
from infra.db import Pagination, RecordModel, transaction
from infra.email import EmailClient, get_email_client
from infra.messaging import Topic
from lib.uuid import parse_uuid

router = APIRouter(tags=["mailbox entries"])

# The default `private, no-cache` (CacheControlMiddleware) lets the browser store
# the response and serve it on a back/forward navigation *without revalidating* —
# so after opening an entry (which marks it read) and hitting browser-back, the
# island renders the stale pre-read snapshot. `no-store` forbids storing it,
# forcing a fresh fetch on history navigation. Scoped to these list endpoints
# rather than the global middleware because they serve mutable per-entry
# read/archive/snooze state that a stale render actively misreports.
_LIST_CACHE_CONTROL = "no-store"

ResourceType = Literal["Chat", "EmailThread", "Post", "Goal"]
_RESOURCE_TYPES: frozenset[str] = frozenset(("Chat", "EmailThread", "Post", "Goal"))


class SnoozeRequest(BaseModel):
    # AwareDatetime rejects naive inputs at the Pydantic layer rather than silently
    # assuming UTC, so the future check below can compare against a tz-aware clock directly.
    snoozed_until: AwareDatetime

    @field_validator("snoozed_until")
    @classmethod
    def _snoozed_until_in_future(cls, value: datetime) -> datetime:
        # Snoozing to a past time drops the entry out of every mailbox view until the
        # unsnooze scan reaps it, so reject it (mirrors SendSideEffectOptions.validate).
        if value <= datetime.now(UTC):
            raise ValueError("Snooze time must be in the future")
        return value


class MailboxEntryResponse(MailboxEntryBase):
    pass


def mailbox_entry_response(entry: MailboxEntry | None) -> MailboxEntryResponse | None:
    return MailboxEntryResponse.from_entry(entry) if entry else None


async def get_mailbox_entry_for_current_user(
    mailbox_entry_id: UUID,
    current_user: User = Depends(get_current_user),
) -> MailboxEntry:
    entry = await MailboxEntry.get_or_none(id=mailbox_entry_id, owner_id=current_user.id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return entry


_EMAIL_CLIENT_ACTIONS: dict[str, str] = {
    "mark_as_read": "mark_thread_read",
    "mark_as_unread": "mark_thread_unread",
    "archive": "archive_thread",
    "unarchive": "unarchive_thread",
    # Snooze archives at the provider; unsnooze restores it. Mirrors email_threads.py.
    "snooze": "archive_thread",
    "unsnooze": "unarchive_thread",
}


async def apply_mailbox_action(
    mailbox: Mailbox,
    entry: MailboxEntry,
    action: str,
    email_client: EmailClient,
    **kwargs,
) -> None:
    resource = await entry.resource_gid.get_or_none()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # EmailThread.mark_as_read/unread iterate messages, so the relation must be loaded
    # before the action runs. Show-page routes get this for free via get_email_thread.
    if isinstance(resource, EmailThread):
        await resource.fetch_related("messages")

    async with transaction() as connection:
        try:
            await getattr(mailbox, action)(resource, using_db=connection, **kwargs)
        except DoesNotExist:
            return

        if isinstance(resource, EmailThread):
            client_action = _EMAIL_CLIENT_ACTIONS.get(action)
            if client_action and resource.is_original_recipient(mailbox.user.id) and resource.external_thread_id:
                await getattr(email_client, client_action)(
                    external_thread_id=resource.external_thread_id,
                    user_id=resource.creator_id,
                    using_db=connection,
                )

    await _broadcast_for_resource(resource)


async def _broadcast_for_resource(resource: RecordModel) -> None:
    if isinstance(resource, Chat):
        await Topic("chats_index", organization_id=resource.organization_id).broadcast()


@router.post("/mailbox_entries/{mailbox_entry_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def api_mailbox_entries_archive(
    mailbox_entry: MailboxEntry = Depends(get_mailbox_entry_for_current_user),
    mailbox: Mailbox = Depends(get_mailbox),
    email_client: EmailClient = Depends(get_email_client),
):
    await apply_mailbox_action(mailbox, mailbox_entry, "archive", email_client)


@router.post("/mailbox_entries/{mailbox_entry_id}/unarchive", status_code=status.HTTP_204_NO_CONTENT)
async def api_mailbox_entries_unarchive(
    mailbox_entry: MailboxEntry = Depends(get_mailbox_entry_for_current_user),
    mailbox: Mailbox = Depends(get_mailbox),
    email_client: EmailClient = Depends(get_email_client),
):
    await apply_mailbox_action(mailbox, mailbox_entry, "unarchive", email_client)


@router.post("/mailbox_entries/{mailbox_entry_id}/mark_read", status_code=status.HTTP_204_NO_CONTENT)
async def api_mailbox_entries_mark_read(
    mailbox_entry: MailboxEntry = Depends(get_mailbox_entry_for_current_user),
    mailbox: Mailbox = Depends(get_mailbox),
    email_client: EmailClient = Depends(get_email_client),
):
    await apply_mailbox_action(mailbox, mailbox_entry, "mark_as_read", email_client)


@router.post("/mailbox_entries/{mailbox_entry_id}/mark_unread", status_code=status.HTTP_204_NO_CONTENT)
async def api_mailbox_entries_mark_unread(
    mailbox_entry: MailboxEntry = Depends(get_mailbox_entry_for_current_user),
    mailbox: Mailbox = Depends(get_mailbox),
    email_client: EmailClient = Depends(get_email_client),
):
    await apply_mailbox_action(mailbox, mailbox_entry, "mark_as_unread", email_client)


@router.post("/mailbox_entries/{mailbox_entry_id}/snooze", status_code=status.HTTP_204_NO_CONTENT)
async def api_mailbox_entries_snooze(
    body: SnoozeRequest,
    mailbox_entry: MailboxEntry = Depends(get_mailbox_entry_for_current_user),
    mailbox: Mailbox = Depends(get_mailbox),
    email_client: EmailClient = Depends(get_email_client),
):
    await apply_mailbox_action(mailbox, mailbox_entry, "snooze", email_client, snoozed_until=body.snoozed_until)


@router.post("/mailbox_entries/{mailbox_entry_id}/unsnooze", status_code=status.HTTP_204_NO_CONTENT)
async def api_mailbox_entries_unsnooze(
    mailbox_entry: MailboxEntry = Depends(get_mailbox_entry_for_current_user),
    mailbox: Mailbox = Depends(get_mailbox),
    email_client: EmailClient = Depends(get_email_client),
):
    await apply_mailbox_action(mailbox, mailbox_entry, "unsnooze", email_client)


#
# Inbox endpoints
#
#


class _AvatarUser(BaseModel):
    id: str
    display_name: str
    picture: str | None = None


class ChatEntryDetail(BaseModel):
    is_group_chat: bool
    is_dm: bool
    collaborator_count: int
    counterparty: _AvatarUser | None = None
    last_message_author: _AvatarUser | None = None
    member_avatars: list[_AvatarUser] = []
    overflow_count: int = 0
    # The message preview rides last_comment + last_comment_author_name ("Alice: hey"), rendered
    # inline rather than as an avatar chip. When a chat-level event (member added/removed, rename,
    # decided) is newer than the last message, preview_kind is "activity" and the event ships raw for the
    # client to phrase (see ChatEntryBody); otherwise "comment".
    preview_kind: Literal["comment", "activity"] = "comment"
    last_comment: str | None = None
    last_comment_author_name: str | None = None
    event_action: str | None = None
    event_details: dict[str, Any] | None = None
    event_actor: _AvatarUser | None = None


class _EventPreviewFields(BaseModel):
    # The second inbox line, summarizing the resource's newest workspace event. Authored events
    # (a comment, or a goal's posted update) carry their text in `last_comment` with
    # `last_comment_author`'s avatar; every other event ships raw — `event_action` + `event_details`
    # (the raw Event diff) + `event_actor` (who did it) — for the client to phrase itself, keeping
    # display strings off the server. `preview_kind` (declared per resource, since goals add an
    # "update" kind) tells the client which shape a given row is.
    last_comment: str | None = None
    last_comment_author: _AvatarUser | None = None
    event_action: str | None = None
    event_details: dict[str, Any] | None = None
    event_actor: _AvatarUser | None = None


class EmailEntryDetail(_EventPreviewFields):
    # Email is the asymmetric three-way: "message" rides the top-level `preview` string (a mail
    # snippet), "comment" rides last_comment as a chip, "activity" pins event_* like posts/goals.
    sender_display: str
    message_count: int
    attachment_count: int
    preview_kind: Literal["message", "comment", "activity"] = "message"
    scheduled_for: datetime | None = None


class PostEntryDetail(_EventPreviewFields):
    # creator_name / group_name form the title-line byline ("by @X for @Y"). is_announcement /
    # is_decided are chips on the title line. Posts have no authored "update" kind (unlike goals),
    # so preview_kind is just comment vs activity.
    creator_name: str
    group_name: str | None = None
    is_announcement: bool
    is_decided: bool
    preview_kind: Literal["comment", "activity"] = "activity"


class GoalEntryDetail(_EventPreviewFields):
    # Evergreen goal state read live off the goal (status/progress/completion). "comment" and
    # "update" are both authored (avatar + last_comment, styled differently); the description rides
    # the entry `preview`.
    status: str
    is_completed: bool
    progress: float | None = None
    preview_kind: Literal["comment", "update", "activity"] = "activity"


class MailboxEntryListItemResponse(BaseModel):
    id: str
    resource_type: Literal["Chat", "EmailThread", "Post", "Goal"]
    href: str
    title: str | None
    preview: str | None
    sender_display: str | None
    last_activity_at: datetime
    is_unread: bool
    is_archived: bool
    is_snoozed: bool
    snoozed_until: datetime | None
    is_assigned_to_me: bool
    is_shared: bool
    email: EmailEntryDetail | None = None
    chat: ChatEntryDetail | None = None
    post: PostEntryDetail | None = None
    goal: GoalEntryDetail | None = None


class MailboxEntryListResponse(PaginatedResponse):
    entries: list[MailboxEntryListItemResponse]
    synced_at: datetime


class MailboxEntryLookupResponse(PaginatedResponse):
    entries: list[MailboxEntryListItemResponse]


def _avatar(user: User | None) -> _AvatarUser | None:
    if not user:
        return None
    return _AvatarUser(id=str(user.id), display_name=user.display_name, picture=user_avatar_url(user))


def _chat_detail(presenter: MailboxEntryPresenter, chat: Chat) -> ChatEntryDetail:
    collaborators = list(chat.workspace.collaborators)
    is_group = chat.group_id is not None
    is_dm = not is_group and len(collaborators) == 2

    counterparty = _avatar(presenter.chat_counterparty)
    last_message_author = None
    if is_group and chat.last_message and chat.last_message.user:
        last_message_author = _avatar(chat.last_message.user)

    member_avatars: list[_AvatarUser] = []
    overflow_count = 0
    if not is_group and len(collaborators) > 2:
        shown = collaborators[:2]
        member_avatars = [a for c in shown if (a := _avatar(c.user))]
        overflow_count = max(len(collaborators) - len(shown), 0)

    entry = presenter.model
    last_comment_author_name = None
    if entry.last_comment and entry.last_comment_author:
        last_comment_author_name = (
            "Me" if entry.last_comment_author_id == entry.owner_id else entry.last_comment_author.display_name
        )

    # A pinned event (member add/remove, rename, decided) means the activity line supersedes the message.
    event = entry.last_event
    return ChatEntryDetail(
        is_group_chat=is_group,
        is_dm=is_dm,
        collaborator_count=len(collaborators),
        counterparty=counterparty,
        last_message_author=last_message_author,
        member_avatars=member_avatars,
        overflow_count=overflow_count,
        preview_kind="activity" if event else "comment",
        last_comment=entry.last_comment,
        last_comment_author_name=last_comment_author_name,
        event_action=event.action.value if event else None,
        event_details=event.details if event else None,
        event_actor=_avatar(event.creator) if event else None,
    )


def _email_detail(presenter: MailboxEntryPresenter) -> EmailEntryDetail:
    # Three-way, resolved from the model's fields the same way the model set them (email/mailbox.py):
    # a pinned last_event is activity; is_preview_comment is a comment chip; otherwise the message
    # snippet on the top-level `preview`.
    entry = presenter.model
    preview_kind: Literal["message", "comment", "activity"]
    if entry.last_event_id:
        preview_kind = "activity"
    elif entry.is_preview_comment:
        preview_kind = "comment"
    else:
        preview_kind = "message"
    return EmailEntryDetail(
        sender_display=format_sender_display(presenter),
        message_count=presenter.email_message_count,
        attachment_count=presenter.email_attachment_count + entry.workspace_attachment_count,
        preview_kind=preview_kind,
        scheduled_for=presenter.scheduled_send_at,
        **_event_preview_fields(entry),
    )


def _event_preview_fields(entry: MailboxEntry) -> dict[str, Any]:
    # The authored text/author (set by the model) plus the pinned activity event (entry.last_event,
    # prefetched by the list query) shipped raw for the client to phrase. Shared by every
    # event-driven detail (posts, goals); see _EventPreviewFields.
    event = entry.last_event
    return dict(
        last_comment=entry.last_comment,
        last_comment_author=_avatar(entry.last_comment_author),
        event_action=event.action.value if event else None,
        event_details=event.details if event else None,
        event_actor=_avatar(event.creator) if event else None,
    )


def _post_detail(entry: MailboxEntry, post: Post, is_decided: bool) -> PostEntryDetail:
    # is_preview_comment marks the authored discussion-comment case; everything else is an activity line.
    preview_kind: Literal["comment", "activity"] = "comment" if entry.is_preview_comment else "activity"
    return PostEntryDetail(
        creator_name=post.creator.display_name if post.creator else "",
        group_name=post.group.name if post.group else None,
        is_announcement=post.is_announcement,
        is_decided=is_decided,
        preview_kind=preview_kind,
        **_event_preview_fields(entry),
    )


def _goal_detail(entry: MailboxEntry, goal: Goal) -> GoalEntryDetail:
    # The model marks the comment case with is_preview_comment; a posted update is the other
    # authored case (carries an author); everything else is a plain activity line the client
    # phrases from entry.last_event (pinned by the model, prefetched by the list query).
    if entry.is_preview_comment:
        preview_kind: Literal["comment", "update", "activity"] = "comment"
    elif entry.last_comment_author_id:
        preview_kind = "update"
    else:
        preview_kind = "activity"
    return GoalEntryDetail(
        status=goal.status.value,
        is_completed=goal.is_completed,
        progress=goal.progress,
        preview_kind=preview_kind,
        **_event_preview_fields(entry),
    )


def _entry_href(url: URL, entry_id: UUID) -> str:
    # Stamp the entry id via include_query_params (correct encoding, house style),
    # then rebuild the relative href the client embeds — url_for returns an
    # absolute URL, so we drop scheme/host back to path?query.
    stamped = url.include_query_params(mailbox_entry_id=str(entry_id))
    return f"{stamped.path}?{stamped.query}" if stamped.query else stamped.path


def _list_item_response(
    presenter: MailboxEntryPresenter,
    *,
    current_user_id: UUID,
    timezone: ZoneInfo,
    helpers: Helpers,
) -> MailboxEntryListItemResponse:
    entry = presenter.model
    resource_type = entry.resource_type
    if resource_type not in _RESOURCE_TYPES:
        raise ValueError(f"Unsupported mailbox entry resource_type: {resource_type!r}")

    # Dispatch on the validated resource_type Literal. MailboxEntryPresenter._load_resources
    # only attaches `resource` when the loaded record's type matches the entry's gid
    # record_type, so each match arm's cast is sound at runtime — resource is either the
    # right concrete type or None (when the user has lost access to the underlying record).
    resource = presenter.resource
    detail_email: EmailEntryDetail | None = None
    detail_chat: ChatEntryDetail | None = None
    detail_post: PostEntryDetail | None = None
    detail_goal: GoalEntryDetail | None = None
    sender_display: str | None = None
    href: str

    match resource_type:
        case "EmailThread":
            detail_email = _email_detail(presenter)
            sender_display = detail_email.sender_display
            record_id = entry.resource_gid.record_id if entry.resource_gid else None
            href = _entry_href(helpers.url_for("email_threads_show", email_thread_id=record_id), entry.id)
        case "Chat":
            chat = cast(Chat | None, resource)
            detail_chat = _chat_detail(presenter, chat) if chat else None
            href = _entry_href(helpers.url_for("chats_show", chat_id=chat.id), entry.id) if chat else "#"
        case "Post":
            post = cast(Post | None, resource)
            detail_post = _post_detail(entry, post, presenter.post_is_decided) if post else None
            href = _entry_href(helpers.url_for("posts_show", post_id=post.id), entry.id) if post else "#"
        case "Goal":
            goal = cast(Goal | None, resource)
            detail_goal = _goal_detail(entry, goal) if goal else None
            href = _entry_href(helpers.url_for("goals_show", goal_id=goal.id), entry.id) if goal else "#"

    preview = html_to_plain_text(entry.preview) if entry.preview else None

    return MailboxEntryListItemResponse(
        id=str(entry.id),
        resource_type=resource_type,
        href=href,
        title=entry.title or None,
        preview=preview,
        sender_display=sender_display,
        last_activity_at=entry.last_activity_at,
        is_unread=entry.is_unread,
        is_archived=entry.is_archived,
        is_snoozed=entry.is_snoozed_now,
        snoozed_until=entry.snoozed_until,
        is_assigned_to_me=entry.assignee_id == current_user_id,
        is_shared=entry.is_shared,
        email=detail_email,
        chat=detail_chat,
        post=detail_post,
        goal=detail_goal,
    )


# Hard cap for lookup-by-ids fetches, bounding the `WHERE id IN (...)` exposed to the network. A
# ranked view section holds every considered candidate, so the cap MUST be >= MAILBOX_VIEW_MAX_ENTRIES
# or hydration truncates and the client silently drops the overflow ids (they resolve to no entry and
# get filtered from the rendered list). Tie it to the generation limit so the two can't drift apart.
_LOOKUP_FETCH_MAX = MAILBOX_VIEW_MAX_ENTRIES


@router.get("/mailbox_entries", response_model=MailboxEntryListResponse)
async def api_mailbox_entries_index(
    response: Response,
    current_user: User = Depends(get_current_user),
    mailbox: Mailbox = Depends(get_mailbox),
    view: MailboxViewName = Query(MailboxViewName.INBOX),
    sort: MailboxSort = Query(MailboxSort.NEWEST),
    cursor: str | None = Query(None),
    helpers: Helpers = Depends(get_helpers),
):
    response.headers["Cache-Control"] = _LIST_CACHE_CONTROL
    queryset = mailbox.filters.for_view(view)
    # Sort applies only to the inbox view today (mirrors mailbox.py:71).
    if view.is_inbox and sort == MailboxSort.OLDEST:
        queryset = queryset.order_by("last_activity_at")

    pagination = await Pagination.create(MailboxEntry, cursor=cursor, queryset=queryset)
    presenters = await MailboxEntryPresenter.create_from_list(pagination, current_user.email)
    timezone = ZoneInfo(current_user.time_zone) if current_user.time_zone else ZoneInfo("UTC")

    entries = [
        _list_item_response(p, current_user_id=current_user.id, timezone=timezone, helpers=helpers) for p in presenters
    ]
    return MailboxEntryListResponse(
        entries=entries,
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
        synced_at=datetime.now(UTC),
    )


@router.get("/mailbox_entries/lookup", response_model=MailboxEntryLookupResponse)
async def api_mailbox_entries_lookup(
    response: Response,
    ids: list[UUID] = Query(...),
    current_user: User = Depends(get_current_user),
    mailbox: Mailbox = Depends(get_mailbox),
    helpers: Helpers = Depends(get_helpers),
):
    response.headers["Cache-Control"] = _LIST_CACHE_CONTROL
    # Mailbox view sections reference entries by id only; the client hydrates
    # them through this endpoint. Scope is the inbox queryset — section rows
    # are filtered to non-archived entries client-side regardless.
    capped_ids = ids[:_LOOKUP_FETCH_MAX]
    if not capped_ids:
        return MailboxEntryLookupResponse(entries=[])
    records = await mailbox.filters.inbox.filter(id__in=capped_ids)
    presenters = await MailboxEntryPresenter.create_from_list(records, current_user.email)
    timezone = ZoneInfo(current_user.time_zone) if current_user.time_zone else ZoneInfo("UTC")
    entries = [
        _list_item_response(p, current_user_id=current_user.id, timezone=timezone, helpers=helpers) for p in presenters
    ]
    return MailboxEntryLookupResponse(entries=entries)


#
# Channels (JSON-mode broadcast handler —
# registered alongside the HTML handler in app/routers/mailbox.py via HandlerRegistry's
# list-of-handlers; both fire on the same NOTIFY broadcast).
#
#


# Aliases legacy route names ("mailbox_index", ...) onto canonical view names ("inbox", ...).
# Needed while the HTML page still subscribes to this stream under the old names.
_VIEW_ALIASES: dict[str, MailboxViewName] = {
    "mailbox_index": MailboxViewName.INBOX,
    "mailbox_archived": MailboxViewName.ARCHIVED,
    "mailbox_assigned_to_me": MailboxViewName.ASSIGNED_TO_ME,
    "mailbox_snoozed": MailboxViewName.SNOOZED,
    "mailbox_sent": MailboxViewName.SENT,
    "mailbox_drafts": MailboxViewName.DRAFTS,
}


class MailboxSyncParams(BaseModel):
    """Typed view of `channel.params` for the mailbox_sync stream.

    Channel params arrive as `dict[str, str]` from the WebSocket query string. This model
    parses them once at the entry of the handler so the body works with real types
    (bool, list[str]) instead of stringly-typed `.get()` calls.
    """

    view: MailboxViewName = MailboxViewName.INBOX
    sort: MailboxSort = MailboxSort.NEWEST
    mailbox_view_mode: bool = False
    view_id: str | None = None
    cached_entry_ids: list[str] = Field(default_factory=list)
    # The subscriber's current page-1 entry ids. Used to compute removed_entry_ids on
    # each broadcast so the client can dedupe entries that have been bumped off page 1
    # by an action elsewhere (archive on page 1 promoting page 2's head, etc.).
    current_entry_ids: list[str] = Field(default_factory=list)

    @field_validator("view", mode="before")
    @classmethod
    def _canonicalize_view(cls, v):
        # Pass-through; downstream enum validation on `view` is the gate that rejects
        # values not in MailboxViewName. This validator only normalizes legacy aliases.
        return _VIEW_ALIASES.get(v, v) if isinstance(v, str) else v

    @field_validator("cached_entry_ids", mode="before")
    @classmethod
    def _parse_cached_entry_ids(cls, v):
        # `cached_entry_ids` feeds a count-exclusion (count_new_entries). A bad payload
        # here only inflates the unread count by a few entries — defensible to soft-fail
        # rather than 422 the whole subscribe.
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (ValueError, TypeError):
                return []
        return v

    @field_validator("current_entry_ids", mode="before")
    @classmethod
    def _parse_current_entry_ids(cls, v):
        # Strict: malformed JSON raises 422. Unlike cached_entry_ids, this drives the
        # cross-page dedupe diff — silently dropping it makes the client believe its
        # locally-cached entries were "kept" when they were actually discarded.
        if isinstance(v, str):
            return json.loads(v)
        return v


@handle_stream("mailbox_sync")
async def mailbox_sync_json_broadcast(channel: Channel, **data) -> None:
    params = MailboxSyncParams.model_validate(channel.params)

    if params.mailbox_view_mode:
        await _emit_mailbox_view_new_messages(channel, params)
        return

    user = channel.current_user
    mailbox = Mailbox(user=user)
    queryset = mailbox.filters.for_view(params.view)

    if params.view.is_inbox and params.sort == MailboxSort.OLDEST:
        queryset = queryset.order_by("last_activity_at")

    pagination = await Pagination.create(MailboxEntry, cursor=None, queryset=queryset)
    new_page_1_ids = {str(entry.id) for entry in pagination}

    # Skip the broadcast when none of the changed entries can affect the subscriber's
    # current page-1 view. Absorbs onboarding/backfill bursts — without it, every
    # coalesced off-page archive sweep still spends presenter work and pushes an
    # event the React client has to diff.
    trigger_entry_ids = {str(eid) for eid in data.get("entry_ids", []) if eid is not None}
    # Canonicalize subscriber-supplied ids through parse_uuid so mixed-case input
    # doesn't produce false positives in the diff. Mirrors count_new_entries().
    canonical_current_ids = {str(uid) for cid in params.current_entry_ids if (uid := parse_uuid(cid))}
    cached_entry_ids = {str(uid) for cid in params.cached_entry_ids if (uid := parse_uuid(cid))}
    if trigger_entry_ids and not (trigger_entry_ids & (cached_entry_ids | canonical_current_ids | new_page_1_ids)):
        return

    presenters = await MailboxEntryPresenter.create_from_list(pagination, user.email)
    timezone = ZoneInfo(user.time_zone) if user.time_zone else ZoneInfo("UTC")

    entries = [
        _list_item_response(p, current_user_id=user.id, timezone=timezone, helpers=channel.helpers).model_dump(
            mode="json"
        )
        for p in presenters
    ]
    removed_entry_ids = sorted(canonical_current_ids - new_page_1_ids)
    await channel.send_event(
        ChannelEventResource.MAILBOX_SYNC,
        ChannelEventAction.UPDATED,
        type="entries",
        entries=entries,
        removed_entry_ids=removed_entry_ids,
        synced_at=datetime.now(UTC).isoformat(),
    )


async def _emit_mailbox_view_new_messages(channel: Channel, params: MailboxSyncParams) -> None:
    if not params.view_id:
        return

    identifier = MailboxViewIdentifier.from_string(params.view_id)
    if not identifier:
        return

    source = await MailboxViewSource.resolve(identifier, channel.current_user)
    if not source:
        return

    cache_data = await source.read_cache()
    # No cache to count against yet (e.g. a first generation is still streaming).
    if not cache_data:
        return

    new_count = await MailboxViewCache.count_new_entries(
        user=channel.current_user,
        since=cache_data.cached_at,
        exclude_entry_ids=set(cache_data.entry_ids),
    )
    # Emit unconditionally, even when new_count == 0 — sync must reset the banner to 0 as
    # mail is read. This is deliberately asymmetric with the subscribe path in
    # mailbox_views.py, which guards on new_count > 0 (a fresh subscriber has no banner to
    # clear). Don't add a `> 0` guard here by analogy.
    await channel.send_event(
        ChannelEventResource.MAILBOX_SYNC,
        ChannelEventAction.UPDATED,
        type="new_messages",
        view_id=params.view_id,
        count=new_count,
    )
