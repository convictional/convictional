from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal, Self, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, model_validator
from tortoise.functions import Count, Max
from tortoise.query_utils import Prefetch

from app.helpers.users import user_avatar_url
from app.jobs.content import ContentIndexingJob, UpdateChatContentAccessJob, invalidate_chat_history_indexing
from app.jobs.notifications import Notifier
from app.models.accounts import Group, GroupMember, User
from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.collaboration.workspace import Collaborator, LinkPreview, ViewStateResolver, Visit
from app.models.workspaces.chat import (
    MAX_CHAT_COLLABORATORS,
    Chat,
    ChatFilters,
    ChatMessage,
)
from app.presenters.internal_link_previews import resolve_preview_files
from app.presenters.link_previews import prepare_link_preview_for_comment
from app.routers.api.link_previews import LinkPreviewResponse, link_preview_response
from app.routers.api.mailbox_entries import MailboxEntryResponse, mailbox_entry_response
from app.routers.api.schemas import (
    GroupResponse,
    PaginatedResponse,
    ReactionUserResponse,
    ReplyPreview,
    UserResponse,
)
from app.routers.api.serializers import fetch_reaction_users, reply_preview, serialize_reactions, user_response
from app.routers.chats import (
    get_chat,
    get_chat_message,
    get_chat_with_indexing,
    index_chat,
)
from app.routers.dependencies import (
    Channel,
    UnclaimedAttachments,
    get_current_user,
    get_org_users,
    handle_stream,
)
from config.enums import (
    AccessAction,
    ChannelEventAction,
    ChannelEventResource,
    ChatType,
    EventAction,
    LinkPreviewStatus,
    ReactionType,
)
from infra.db import GlobalID, Pagination, allow_soft_deleted, transaction
from infra.jobs import enqueue_job
from infra.messaging import Topic

CHAT_MESSAGES_PER_PAGE = 50

# Messages fetched on *each side* of an anchor when jumping to a quoted message.
# Half of CHAT_MESSAGES_PER_PAGE so the combined window (older + anchor + newer)
# lands at ~one page rather than two.
CHAT_AROUND_CONTEXT = CHAT_MESSAGES_PER_PAGE // 2

MessageDirection = Literal["older", "newer"]

router = APIRouter(dependencies=[Depends(index_chat, scope="function")], tags=["chats"])


#
# Response models
#
#


class ChatMessageResponse(BaseModel):
    id: str
    global_id: str = Field(description="GlobalID used to reference this message across resources.")
    content: str
    created_at: datetime
    edited_at: datetime | None
    reactions: dict[str, list[ReactionUserResponse]]
    user: UserResponse
    link_preview: LinkPreviewResponse | None
    reply_to: ReplyPreview | None = None


class ChatCollaboratorResponse(BaseModel):
    id: str
    user: UserResponse

    @classmethod
    def from_collaborator(cls, collaborator: Collaborator) -> "ChatCollaboratorResponse | None":
        if not collaborator.user:
            return None
        return cls(id=str(collaborator.id), user=user_response(collaborator.user))


class ChatListItemResponse(BaseModel):
    id: str
    type: ChatType
    name: str
    collaborator_count: int
    collaborators: list[ChatCollaboratorResponse] | None = None
    latest_message: ChatMessageResponse | None
    user: UserResponse | None
    picture: str | None
    is_unread: bool = False
    is_archived: bool = False
    snoozed_until: datetime | None = None


class ChatListResponse(PaginatedResponse):
    chats: list[ChatListItemResponse]


class ContactResponse(BaseModel):
    id: str
    type: str
    name: str
    collaborator_count: int
    picture: str | None


class ContactListResponse(PaginatedResponse):
    contacts: list[ContactResponse]


class ChatDetailResponse(BaseModel):
    chat_id: str
    workspace_id: str
    chat_title: str
    type: ChatType
    is_group_chat: bool
    group_id: str | None = None
    collaborators: list[ChatCollaboratorResponse] = []
    # Whether this chat supports @-mentions (multi/group do; dm/self don't). The
    # client sources mention candidates from the organizationMembers store,
    # filtered to this chat's collaborators.
    supports_mentions: bool = False
    last_read_at: str | None = None
    unread_message_count: int = 0
    mailbox: MailboxEntryResponse | None = None


class MessageListResponse(PaginatedResponse):
    messages: list[ChatMessageResponse]


class MessageWindowResponse(MessageListResponse):
    # The window is a bidirectional slice of the message sequence. next_cursor /
    # has_more are the OLDER direction, so the client's existing loadMore keeps
    # walking further back unchanged. at_tail answers the only remaining question
    # — "is the newest message in this window the live tail?" — which the client
    # uses to decide whether to show the jump-to-latest affordance and whether it
    # still needs to paginate forward (direction=newer) to reach the tail.
    at_tail: bool


class ChatCreatedResponse(BaseModel):
    chat_id: str
    workspace_id: str
    type: ChatType
    name: str
    collaborators: list[ChatCollaboratorResponse] | None = None
    recipient: UserResponse | None
    group: GroupResponse | None
    supports_mentions: bool


class GroupMatchResponse(BaseModel):
    id: str
    name: str


class ChatLookupResponse(PaginatedResponse):
    matches: list[ChatListItemResponse] = []
    match_group: GroupMatchResponse | None = None


class AddCollaboratorResponse(BaseModel):
    chat_id: str
    added: bool


class RenameChatResponse(BaseModel):
    id: str
    title: str | None
    chat_title: str


class MessageResponse(BaseModel):
    message: ChatMessageResponse


#
# Request models
#
#


class CreateChatRequest(BaseModel):
    recipient_ids: list[UUID] | None = Field(None, max_length=MAX_CHAT_COLLABORATORS)
    group_id: UUID | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> Self:
        has_recipients = bool(self.recipient_ids)
        if has_recipients == bool(self.group_id):
            raise ValueError("Provide exactly one of recipient_ids or group_id")
        return self


class AddCollaboratorRequest(BaseModel):
    user_id: UUID
    share_history: bool = True


class RenameChatRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ChatMessageBaseRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    skip_link_preview: bool = False
    attachment_claim_id: UUID | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("content must not be blank")
        return stripped


class ChatMessageRequest(ChatMessageBaseRequest):
    # Send-only: the quote-reply target. Edit has no reply affordance, so this
    # lives here rather than on the base — the edit request must not advertise a
    # field it silently ignores.
    reply_to_id: UUID | None = None


class EditChatMessageRequest(ChatMessageBaseRequest):
    # Edit-only: the editor reports which existing attachment IDs its current
    # content still references. The handler uses this list to decide which
    # already-claimed inline attachments to keep — bypassing the brittle
    # URL-substring match in `cleanup_unreferenced_attachments`, which can
    # mis-fire after a ProseMirror serialize/parse round trip.
    retained_attachment_ids: list[UUID] | None = None


#
# Helpers
#
#


def _chat_topic(chat: Chat) -> Topic:
    return Topic("chat", chat_id=chat.id, workspace_id=chat.workspace_id)


def _chats_index_topic(chat: Chat) -> Topic:
    return Topic("chats_index", organization_id=chat.organization_id)


def _collaborators_response(chat: Chat) -> list[ChatCollaboratorResponse]:
    return [
        response
        for c in chat.workspace.collaborators
        if (response := ChatCollaboratorResponse.from_collaborator(c)) is not None
    ]


async def _reply_to_prefetch() -> Prefetch:
    async with allow_soft_deleted():
        return Prefetch("reply_to", queryset=ChatMessage.filter().select_related("user"))


def _message_response(
    message: ChatMessage,
    users_by_id: dict[UUID, User] | None = None,
    files_by_url: dict[str, dict[str, Any]] | None = None,
    *,
    include_reply: bool = True,
) -> ChatMessageResponse:
    lp = message.link_preview
    preview = link_preview_response(lp, files_by_url) if lp and lp.status == LinkPreviewStatus.READY else None
    edited_at = message.updated_at if message.was_edited else None
    reply_to = None
    if include_reply and message.reply_to_id and message.reply_to:
        reply_to = reply_preview(message.reply_to)
    return ChatMessageResponse(
        id=str(message.id),
        global_id=str(message.global_id),
        content=message.content,
        created_at=message.created_at,
        edited_at=edited_at,
        reactions=serialize_reactions(message.reactions, users_by_id or {}),
        user=user_response(message.user),
        link_preview=preview,
        reply_to=reply_to,
    )


async def _serialize_messages(
    messages: list[ChatMessage],
    current_user: User,
    users_by_id: dict[UUID, User] | None = None,
    *,
    include_reply: bool = True,
) -> list[ChatMessageResponse]:
    # Resolve file-card metadata for every attachment-link preview in one batch (vs a round-trip
    # per preview), gated by the reading user's access, then build each response with it.
    files_by_url = await resolve_preview_files([message.link_preview for message in messages], current_user)
    return [_message_response(message, users_by_id, files_by_url, include_reply=include_reply) for message in messages]


def _message_keyset_cursor(message: ChatMessage) -> str:
    # The keyset cursor pointing at `message`, byte-compatible with what Pagination
    # emits — so it can seed either pagination direction off an existing row.
    return Pagination.encode_cursor([("created_at", message.created_at), ("id", message.id)])


async def _paginate_messages(
    chat_id: UUID,
    cursor: str | None = None,
    direction: MessageDirection = "older",
    per_page: int = CHAT_MESSAGES_PER_PAGE,
) -> tuple[list[ChatMessage], Pagination]:
    reply_prefetch = await _reply_to_prefetch()
    # "older" walks the descending keyset and is reversed back to chronological
    # order; "newer" walks the ascending keyset (mirroring the window's newer
    # half) and is already chronological. Either way the caller receives messages
    # oldest-first within the page.
    ordering = "created_at" if direction == "newer" else "-created_at"
    queryset = (
        ChatMessage.filter(chat_id=chat_id)
        .order_by(ordering)
        .prefetch_related("user__avatar_file", "link_preview", reply_prefetch)
    )
    pagination = await Pagination.create(ChatMessage, cursor=cursor, queryset=queryset, per_page=per_page)
    messages = pagination.results if direction == "newer" else list(reversed(pagination.results))
    return messages, pagination


async def _build_message_list(
    chat_id: UUID, current_user: User, cursor: str | None = None, direction: MessageDirection = "older"
) -> MessageListResponse:
    messages, pagination = await _paginate_messages(chat_id, cursor=cursor, direction=direction)
    users_by_id = await fetch_reaction_users(messages)
    return MessageListResponse(
        messages=await _serialize_messages(messages, current_user, users_by_id),
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


async def _build_message_window(chat_id: UUID, current_user: User, anchor: ChatMessage) -> MessageWindowResponse:
    # Drive the existing keyset engine from a synthesized anchor cursor rather
    # than hand-rolling the comparator. The older direction's next_cursor is then
    # a valid loadMore cursor for the unchanged list endpoint.
    anchor_cursor = _message_keyset_cursor(anchor)

    # Both halves reuse _paginate_messages so the window stays query-identical to
    # the loadMore list endpoint. The older half's next_cursor is therefore a
    # valid loadMore cursor for the unchanged list endpoint. The newer half is
    # only used to learn whether the window already reaches the live tail
    # (at_tail); the client closes any remaining gap by forward-paginating the
    # list endpoint (direction=newer&after=…), so its cursor isn't surfaced.
    older_msgs, older = await _paginate_messages(
        chat_id, cursor=anchor_cursor, direction="older", per_page=CHAT_AROUND_CONTEXT
    )
    newer_msgs, newer = await _paginate_messages(
        chat_id, cursor=anchor_cursor, direction="newer", per_page=CHAT_AROUND_CONTEXT
    )

    # _paginate_messages returns each half oldest-first, so the chronological
    # window is older_msgs ++ anchor ++ newer_msgs. Dedup guards against the
    # anchor reappearing across the two halves' keyset boundaries.
    window_rows: list[ChatMessage] = []
    seen_ids: set[UUID] = set()
    for message in [*older_msgs, anchor, *newer_msgs]:
        if message.id in seen_ids:
            continue
        seen_ids.add(message.id)
        window_rows.append(message)

    users_by_id = await fetch_reaction_users(window_rows)
    return MessageWindowResponse(
        messages=await _serialize_messages(window_rows, current_user, users_by_id),
        next_cursor=older.next_cursor,
        has_more=older.has_next,
        at_tail=not newer.has_next,
    )


async def _reload_message_response(message_id: UUID, current_user: User) -> MessageResponse:
    reply_prefetch = await _reply_to_prefetch()
    message = await ChatMessage.get(id=message_id).prefetch_related(
        "user__avatar_file", "link_preview", reply_prefetch
    )
    users_by_id = await fetch_reaction_users([message])
    [response] = await _serialize_messages([message], current_user, users_by_id)
    return MessageResponse(message=response)


def _chat_list_item_response(
    chat: Chat, current_user_id: UUID, entry: MailboxEntry | None = None
) -> ChatListItemResponse:
    last_msg = chat.last_message if chat.last_message_id else None
    name = chat.resolved_title(current_user_id)
    collaborators = list(chat.workspace.collaborators)

    if chat.type.is_self:
        user = None
        picture = None
        collaborators_response = None
    elif chat.type.is_dm:
        other_collabs = [c for c in collaborators if c.user_id != current_user_id]
        other = other_collabs[0] if other_collabs else None
        user = user_response(other.user) if other and other.user else None
        picture = user_avatar_url(other.user) if other and other.user else None
        collaborators_response = None
    elif chat.type.is_multi:
        user = None
        picture = None
        collaborators_response = _collaborators_response(chat)
    else:
        user = None
        picture = None
        collaborators_response = None

    return ChatListItemResponse(
        id=str(chat.id),
        type=chat.type,
        name=name,
        collaborator_count=len(collaborators),
        collaborators=collaborators_response,
        latest_message=_message_response(last_msg, include_reply=False) if last_msg else None,
        user=user,
        picture=picture,
        is_unread=entry.is_unread if entry else False,
        is_archived=entry.is_archived if entry else False,
        snoozed_until=entry.snoozed_until if entry else None,
    )


async def _fetch_mailbox_entries(user_id: UUID, chat_ids: list[UUID]) -> dict[UUID, MailboxEntry]:
    gids = [str(GlobalID.create("Chat", cid)) for cid in chat_ids]
    entries = await MailboxEntry.filter(owner_id=user_id, resource_gid__in=gids).all()
    result: dict[UUID, MailboxEntry] = {}
    for entry in entries:
        gid = GlobalID.parse(str(entry.resource_gid))
        result[gid.record_id] = entry
    return result


def _user_chats_queryset(user: User):
    return (
        Chat.filter(
            ChatFilters.by_organization(user.organization_id),
            ChatFilters.nondeleted,
            ChatFilters.active_for_user(user.id),
        )
        .prefetch_related(
            "last_message__user__avatar_file",
            "last_message__link_preview",
            "workspace__collaborators__user__avatar_file",
        )
        .order_by("-last_message_at")
    )


def _chat_match_sort_key(chat: Chat, expected_collaborator_count: int) -> tuple[bool, bool, float]:
    last_message_at = getattr(chat, "last_message_at", None)
    is_exact_match = len(chat.workspace.collaborators) == expected_collaborator_count
    recency = -last_message_at.timestamp() if last_message_at else 0
    # Sort: exact match first, then chats with messages by recency, then empty chats
    return (not is_exact_match, last_message_at is None, recency)


async def _chat_ids_containing_all_collaborators(user_ids: list[UUID], organization_id: UUID) -> list[UUID]:
    rows = await (
        Collaborator.filter(user_id__in=user_ids, workspace__organization_id=organization_id)
        .annotate(match_count=Count("id"))
        .group_by("workspace_id")
        .values("workspace_id", "match_count")
    )
    matching_workspace_ids = [row["workspace_id"] for row in rows if row["match_count"] == len(user_ids)]
    if not matching_workspace_ids:
        return []
    return cast(
        list[UUID],
        await Chat.filter(workspace_id__in=matching_workspace_ids, organization_id=organization_id).values_list(
            "id", flat=True
        ),
    )


async def _build_chat_created_response(
    chat: Chat,
    current_user: User,
    *,
    recipient: User | None = None,
    group: Group | None = None,
) -> ChatCreatedResponse:
    await chat.fetch_related("workspace__collaborators__user__avatar_file")

    if group:
        name = group.name
        group_resp: GroupResponse | None = GroupResponse(id=str(group.id), name=group.name)
    elif recipient:
        name = recipient.display_name
        group_resp = None
    else:
        name = chat.resolved_title(current_user.id)
        group_resp = None

    return ChatCreatedResponse(
        chat_id=str(chat.id),
        workspace_id=str(chat.workspace_id),
        type=chat.type,
        name=name,
        collaborators=_collaborators_response(chat) if chat.type.is_multi else None,
        recipient=user_response(recipient) if recipient else None,
        group=group_resp,
        supports_mentions=chat.supports_mentions,
    )


async def save_new_chat_message(
    chat: Chat,
    current_user: User,
    content: str,
    link_preview_data: tuple[str, dict[str, Any]] | None,
    unclaimed_attachments: UnclaimedAttachments | None = None,
    reply_to_id: UUID | None = None,
) -> ChatMessage:
    async with transaction() as connection:
        message = await ChatMessage.create(
            chat_id=chat.id,
            user_id=current_user.id,
            content=content,
            reply_to_id=reply_to_id,
            using_db=connection,
        )
        notifier = Notifier(chat, current_user)
        async with notifier.record_and_notify(
            EventAction.CHAT_MESSAGE_CREATED,
            recordable=message,
            using_db=connection,
        ) as recording:
            if chat.supports_mentions:
                await recording.resolve_mentions(content)
        if unclaimed_attachments:
            await unclaimed_attachments.claim_for_comment(message, using_db=connection)
        if link_preview_data:
            await LinkPreview.associate(ChatMessage, message.id, link_preview_data, using_db=connection)
        await Chat.sync_last_message(chat.id, latest_message=message, using_db=connection)
        # Sending a message implies the sender has seen everything up to and including it, so
        # advance their Visit to this event. Without this, the sender's own messages land after
        # their Visit.last_event and would appear above the "new messages" divider on next open.
        await Visit.record(current_user.id, chat.workspace_id, last_event_id=recording.event.id, using_db=connection)

    await chat.refresh_from_db()
    await message.broadcast_created()
    await Topic("chats_index", organization_id=chat.organization_id).broadcast()
    return message


async def save_chat_message_deletion(chat: Chat, message: ChatMessage, current_user: User) -> None:
    message_created_at = message.created_at
    async with transaction() as connection:
        notifier = Notifier(chat, current_user)
        async with notifier.record_and_notify(
            EventAction.CHAT_MESSAGE_DELETED,
            recordable=message,
            using_db=connection,
        ):
            await message.soft_delete(using_db=connection)
        await Chat.sync_last_message(chat.id, using_db=connection)
        await invalidate_chat_history_indexing(
            chat.organization_id, str(chat.global_id), message_created_at, using_db=connection
        )

    await chat.refresh_from_db()
    await message.broadcast_deleted()
    await Topic("chats_index", organization_id=chat.organization_id).broadcast()


#
# Endpoints
#
#


@router.get("/chats", response_model=ChatListResponse)
async def api_chats_index(
    current_user: User = Depends(get_current_user),
    cursor: str | None = Query(None),
):
    pagination = await Pagination.create(Chat, cursor=cursor, queryset=_user_chats_queryset(current_user))

    chat_ids = [chat.id for chat in pagination.results]
    mailbox_entries = await _fetch_mailbox_entries(current_user.id, chat_ids)

    chats = [
        _chat_list_item_response(chat, current_user.id, mailbox_entries.get(chat.id)) for chat in pagination.results
    ]

    return ChatListResponse(
        chats=chats,
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


@router.get("/chats/contacts", response_model=ContactListResponse)
async def api_chats_contacts(
    current_user: User = Depends(get_current_user),
    org_users: list[User] = Depends(get_org_users),
):
    chat_user_ids, groups_with_chats = await Chat.active_partners_for(current_user)

    user_groups = await Group.filter(
        members__user_id=current_user.id,
        organization_id=current_user.organization_id,
        deleted_at__isnull=True,
    ).prefetch_related(Group.active_members_prefetch())

    contacts: list[ContactResponse] = []
    for group in user_groups:
        if group.id not in groups_with_chats:
            contacts.append(
                ContactResponse(
                    id=str(group.id),
                    type="group",
                    name=group.name,
                    collaborator_count=len(group.members),
                    picture=None,
                )
            )
    for user in org_users:
        if user.id != current_user.id and user.id not in chat_user_ids:
            contacts.append(
                ContactResponse(
                    id=str(user.id),
                    type="dm",
                    name=user.display_name,
                    collaborator_count=0,
                    picture=user_avatar_url(user),
                )
            )

    contacts.sort(key=lambda c: c.name.lower())
    return ContactListResponse(contacts=contacts)


@router.get("/chats/lookup", response_model=ChatLookupResponse)
async def api_lookup_chat(
    user_ids: list[UUID] = Query(...),
    current_user: User = Depends(get_current_user),
):
    parsed_ids = list(dict.fromkeys(user_ids))

    if len(parsed_ids) < 2 or len(parsed_ids) > MAX_CHAT_COLLABORATORS:
        return ChatLookupResponse()

    if current_user.id not in parsed_ids:
        return ChatLookupResponse()

    matching_chat_ids = await _chat_ids_containing_all_collaborators(parsed_ids, current_user.organization_id)
    matches: list[ChatListItemResponse] = []
    exact_member_chat_exists = False
    if matching_chat_ids:
        chats = await (
            Chat.filter(
                ChatFilters.by_organization(current_user.organization_id),
                ChatFilters.by_ids(matching_chat_ids),
                ChatFilters.nondeleted,
            )
            .annotate(last_message_at=Max("messages__created_at"))
            .prefetch_related(
                "workspace__collaborators__user__avatar_file",
                "last_message__user__avatar_file",
                "last_message__link_preview",
            )
        )
        # Surface the exact-membership chat first, then sort the rest by recency (empty chats last)
        chats.sort(key=lambda c: _chat_match_sort_key(c, len(parsed_ids)))
        mailbox_entries = await _fetch_mailbox_entries(current_user.id, [c.id for c in chats])
        matches = [_chat_list_item_response(c, current_user.id, mailbox_entries.get(c.id)) for c in chats]
        exact_member_chat_exists = any(len(c.workspace.collaborators) == len(parsed_ids) for c in chats)

    # Only surface the match_group fallback when no existing chat covers the exact membership
    if exact_member_chat_exists:
        return ChatLookupResponse(matches=matches)

    group = await Chat.find_matching_group(parsed_ids, current_user.organization_id)
    if group:
        return ChatLookupResponse(
            matches=matches,
            match_group=GroupMatchResponse(id=str(group.id), name=group.name),
        )

    return ChatLookupResponse(matches=matches)


@router.get("/chats/{chat_id}", response_model=ChatDetailResponse)
async def api_chat_detail(
    chat: Chat = Depends(get_chat),
    current_user: User = Depends(get_current_user),
):
    # Unread pivots on the view-state event cursor (matches Posts/Goals). last_viewed_event_at is
    # that cursor event's created_at — the timestamp the frontend uses to draw the "new messages"
    # divider. When the user has no Visit yet, fall back to when they joined the workspace so
    # messages since joining are counted.
    view_state = await ViewStateResolver.for_user_in_workspace(current_user.id, chat.workspace_id)
    last_read_at = view_state.last_viewed_event_at

    joined_at = next(
        (c.created_at for c in chat.workspace.collaborators if c.user_id == current_user.id),
        None,
    )
    unread_pivot = last_read_at or joined_at
    unread_count = 0
    if unread_pivot:
        unread_count = (
            await ChatMessage.filter(
                chat_id=chat.id,
                created_at__gt=unread_pivot,
                deleted_at__isnull=True,
            )
            .exclude(user_id=current_user.id)
            .count()
        )

    entry = await MailboxEntry.get_or_none(
        owner_id=current_user.id,
        resource_gid=str(GlobalID.create("Chat", chat.id)),
    )

    return ChatDetailResponse(
        chat_id=str(chat.id),
        workspace_id=str(chat.workspace_id),
        chat_title=chat.resolved_title(current_user.id),
        type=chat.type,
        is_group_chat=bool(chat.group_id),
        group_id=str(chat.group_id) if chat.group_id else None,
        collaborators=_collaborators_response(chat),
        supports_mentions=chat.supports_mentions,
        last_read_at=last_read_at.isoformat() if last_read_at else None,
        unread_message_count=unread_count,
        mailbox=mailbox_entry_response(entry),
    )


@router.post("/chats", response_model=ChatCreatedResponse, status_code=status.HTTP_200_OK)
async def api_find_or_create_chat(
    body: CreateChatRequest,
    current_user: User = Depends(get_current_user),
):
    if body.group_id:
        group = await Group.get(id=body.group_id, organization_id=current_user.organization_id)
        if not await GroupMember.filter(group_id=group.id, user_id=current_user.id).exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        async with transaction() as connection:
            chat, _ = await Chat.find_or_create_for_group(group, creator_user_id=current_user.id, using_db=connection)
        return await _build_chat_created_response(chat, current_user, group=group)

    recipient_ids = list(dict.fromkeys(body.recipient_ids or []))
    if recipient_ids == [current_user.id]:
        async with transaction() as connection:
            chat, _ = await Chat.find_or_create_self(current_user, using_db=connection)
        return await _build_chat_created_response(chat, current_user)

    if current_user.id in recipient_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot include yourself alongside other recipients.",
        )

    recipients = await User.active.filter(
        id__in=recipient_ids, organization_id=current_user.organization_id
    ).select_related("avatar_file")
    if len(recipients) != len(recipient_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more recipients not found.")

    if len(recipients) == 1:
        async with transaction() as connection:
            chat, _ = await Chat.find_or_create_direct(current_user, recipients[0], using_db=connection)
        return await _build_chat_created_response(chat, current_user, recipient=recipients[0])

    async with transaction() as connection:
        chat, _ = await Chat.find_or_create_multi(current_user, recipients, using_db=connection)
    return await _build_chat_created_response(chat, current_user)


@router.post("/chats/{chat_id}/collaborators", response_model=AddCollaboratorResponse)
async def api_add_collaborator(
    body: AddCollaboratorRequest,
    chat: Chat = Depends(get_chat),
    current_user: User = Depends(get_current_user),
):
    user_to_add = await User.active.get_or_none(id=body.user_id, organization_id=current_user.organization_id)
    if not user_to_add:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    try:
        chat.validate_add_collaborator(body.user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from None

    if body.share_history:
        async with transaction() as connection:
            await chat.add_collaborator(user_to_add, added_by=current_user, using_db=connection)

        await Mailbox.sync(chat)
        await enqueue_job(ContentIndexingJob.from_model(chat.organization_id, chat))
        await enqueue_job(
            UpdateChatContentAccessJob(chat_id=chat.id, user_id=user_to_add.id, action=AccessAction.ADD, unique=True)
        )
        await _chat_topic(chat).broadcast(collaborator_added=str(user_to_add.id))
        await _chats_index_topic(chat).broadcast()

        return AddCollaboratorResponse(chat_id=str(chat.id), added=True)

    all_collaborator_ids = list(chat.collaboration.accessor_ids) + [body.user_id]
    recipients = await User.active.filter(
        id__in=[uid for uid in all_collaborator_ids if uid != current_user.id],
        organization_id=current_user.organization_id,
    )

    async with transaction() as connection:
        new_chat, created = await Chat.find_or_create_multi(current_user, list(recipients), using_db=connection)

    if created:
        await Mailbox.sync(new_chat)
        await enqueue_job(ContentIndexingJob.from_model(new_chat.organization_id, new_chat))
        await _chats_index_topic(new_chat).broadcast()

    return AddCollaboratorResponse(chat_id=str(new_chat.id), added=False)


@router.delete("/chats/{chat_id}/collaborators/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_remove_collaborator(
    user_id: UUID,
    chat: Chat = Depends(get_chat),
    current_user: User = Depends(get_current_user),
):
    try:
        async with transaction() as connection:
            result = await chat.remove_collaborator(user_id, removed_by_id=current_user.id, using_db=connection)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from None

    await Mailbox.sync(chat)
    await enqueue_job(ContentIndexingJob.from_model(chat.organization_id, chat))
    if result.archived:
        await _chat_topic(chat).broadcast(
            chat_archived=True,
            conflicting_dm_id=str(result.conflicting_dm_id) if result.conflicting_dm_id else None,
        )
    else:
        await enqueue_job(
            UpdateChatContentAccessJob(chat_id=chat.id, user_id=user_id, action=AccessAction.REMOVE, unique=True)
        )
        await _chat_topic(chat).broadcast(collaborator_removed=str(user_id))
    await _chats_index_topic(chat).broadcast()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/chats/{chat_id}", status_code=status.HTTP_200_OK, response_model=RenameChatResponse)
async def api_rename_chat(
    body: RenameChatRequest,
    chat: Chat = Depends(get_chat),
    current_user: User = Depends(get_current_user),
):
    try:
        await chat.rename(body.title, current_user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from None

    await Mailbox.sync(chat)
    await _chats_index_topic(chat).broadcast()

    return {"id": str(chat.id), "title": chat.title, "chat_title": chat.resolved_title(current_user.id)}


@router.get("/chats/{chat_id}/messages", response_model=MessageListResponse)
async def api_list_chat_messages(
    chat: Chat = Depends(get_chat),
    current_user: User = Depends(get_current_user),
    cursor: str | None = Query(None),
    direction: MessageDirection = Query("older"),
    after: UUID | None = Query(None),
):
    # direction=older (default) walks back through history; direction=newer walks
    # forward toward the live tail, which is how the client closes the gap from a
    # historical window (around endpoint) down to at_tail. In both cases
    # next_cursor/has_more describe the requested direction and messages come back
    # oldest-first within the page; the client derives at_tail = not has_more.
    #
    # `after` seeds the first forward page from that message's keyset position.
    # Subsequent forward pages pass the opaque next_cursor instead, so `after` is
    # ignored once an explicit cursor is present.
    if direction == "newer" and after is not None and cursor is None:
        seed = await ChatMessage.get_or_none(id=after, chat_id=chat.id)
        if seed is None or seed.is_deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        cursor = _message_keyset_cursor(seed)
    return await _build_message_list(chat.id, current_user, cursor=cursor, direction=direction)


@router.get("/chats/{chat_id}/messages/around/{message_id}", response_model=MessageWindowResponse)
async def api_chat_messages_around(
    message_id: UUID,
    chat: Chat = Depends(get_chat),
    current_user: User = Depends(get_current_user),
):
    # Inline anchor lookup, not the get_chat_message dependency: that uses .get()
    # (raises 500, not 404) and prefetches neither the avatar nor reply data.
    anchor = await ChatMessage.get_or_none(id=message_id, chat_id=chat.id).prefetch_related(
        "user__avatar_file", "link_preview", await _reply_to_prefetch()
    )
    if anchor is None or anchor.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return await _build_message_window(chat.id, current_user, anchor)


@router.post(
    "/chats/{chat_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_send_chat_message(
    body: ChatMessageRequest,
    chat: Chat = Depends(get_chat_with_indexing),
    current_user: User = Depends(get_current_user),
):
    link_preview_data = None
    if not body.skip_link_preview:
        link_preview_data = await prepare_link_preview_for_comment(body.content, current_user)

    if body.reply_to_id:
        reply_exists = await ChatMessage.filter(id=body.reply_to_id, chat_id=chat.id).exists()
        if not reply_exists:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="reply_to_id not found in this chat",
            )

    unclaimed = None
    if body.attachment_claim_id:
        unclaimed = await UnclaimedAttachments.find(body.attachment_claim_id, current_user.id)
    message = await save_new_chat_message(
        chat, current_user, body.content, link_preview_data, unclaimed, body.reply_to_id
    )
    return await _reload_message_response(message.id, current_user)


@router.patch("/chats/{chat_id}/messages/{message_id}", response_model=MessageResponse)
async def api_edit_chat_message(
    body: EditChatMessageRequest,
    chat: Chat = Depends(get_chat_with_indexing),
    message: ChatMessage = Depends(get_chat_message),
    current_user: User = Depends(get_current_user),
):
    if message.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    link_preview_data = None
    if not body.skip_link_preview:
        link_preview_data = await prepare_link_preview_for_comment(body.content, current_user)

    async with transaction() as connection:
        notifier = Notifier(chat, current_user)
        async with notifier.record_and_notify(
            EventAction.CHAT_MESSAGE_EDITED,
            recordable=message,
            using_db=connection,
        ) as recording:
            message.content = body.content
            await message.save(using_db=connection)
            if chat.supports_mentions:
                await recording.resolve_mentions(body.content)
        if body.attachment_claim_id or body.retained_attachment_ids is not None:
            unclaimed = (
                await UnclaimedAttachments.find(body.attachment_claim_id, current_user.id)
                if body.attachment_claim_id
                else UnclaimedAttachments(uuid4(), [])
            )
            await unclaimed.claim_for_comment(
                message,
                retained_attachment_ids=body.retained_attachment_ids,
                using_db=connection,
            )
        await LinkPreview.associate(ChatMessage, message.id, link_preview_data, using_db=connection)

    await message.broadcast_updated()
    return await _reload_message_response(message.id, current_user)


@router.delete("/chats/{chat_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_chat_message(
    chat: Chat = Depends(get_chat_with_indexing),
    message: ChatMessage = Depends(get_chat_message),
    current_user: User = Depends(get_current_user),
):
    if message.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    await save_chat_message_deletion(chat, message, current_user)


@router.post("/chats/{chat_id}/messages/{message_id}/reactions", response_model=MessageResponse)
async def api_toggle_chat_message_reaction(
    reaction_type: ReactionType = Query(...),
    message: ChatMessage = Depends(get_chat_message),
    current_user: User = Depends(get_current_user),
):
    async with transaction() as conn:
        locked = await ChatMessage.select_for_update().using_db(conn).get(id=message.id)
        locked.toggle_reaction(current_user.id, reaction_type)
        await locked.save(update_fields=["reactions"], using_db=conn)
    await locked.broadcast_updated()
    return await _reload_message_response(message.id, current_user)


#
# Channels
#
#


async def _send_message_event(channel: Channel, message_id: UUID, action: ChannelEventAction) -> None:
    reply_prefetch = await _reply_to_prefetch()
    message = await ChatMessage.get_or_none(id=message_id).prefetch_related(
        "user__avatar_file", "link_preview", reply_prefetch
    )
    if not message:
        return
    users_by_id = await fetch_reaction_users([message])
    [response] = await _serialize_messages([message], channel.current_user, users_by_id)
    await channel.send_event(
        ChannelEventResource.CHAT_MESSAGE,
        action,
        **response.model_dump(mode="json"),
    )


async def _typing_event(channel: Channel, data: dict[str, Any]) -> None:
    typing_user_ids = data.get("typing_user_ids")
    if not isinstance(typing_user_ids, list):
        typing_user_ids = []
    typing_user_ids = typing_user_ids[:20]
    users = (
        await User.filter(
            id__in=typing_user_ids,
            organization_id=channel.current_user.organization_id,
        )
        .select_related("avatar_file")
        .all()
        if typing_user_ids
        else []
    )
    await channel.send_event(
        ChannelEventResource.CHAT_TYPING,
        ChannelEventAction.TYPING,
        users=[{"id": str(u.id), "display_name": u.display_name, "picture": user_avatar_url(u)} for u in users],
    )


async def _collaborator_added_event(channel: Channel, data: dict[str, Any]) -> None:
    user = await User.get_or_none(
        id=data["collaborator_added"], organization_id=channel.current_user.organization_id
    ).select_related("avatar_file")
    if not user:
        return
    resp = user_response(user)
    if not resp:
        return
    await channel.send_event(
        ChannelEventResource.CHAT_COLLABORATOR,
        ChannelEventAction.ADDED,
        user=resp.model_dump(mode="json"),
    )


async def _collaborator_removed_event(channel: Channel, data: dict[str, Any]) -> None:
    await channel.send_event(
        ChannelEventResource.CHAT_COLLABORATOR,
        ChannelEventAction.REMOVED,
        user_id=str(data["collaborator_removed"]),
    )


async def _chat_archived_event(channel: Channel, data: dict[str, Any]) -> None:
    await channel.send_event(
        ChannelEventResource.CHAT_COLLABORATOR,
        ChannelEventAction.ARCHIVED,
        conflicting_dm_id=data.get("conflicting_dm_id"),
    )


async def _new_message_event(channel: Channel, data: dict[str, Any]) -> None:
    await _send_message_event(channel, data["new_message_id"], ChannelEventAction.NEW_MESSAGE)


async def _updated_message_event(channel: Channel, data: dict[str, Any]) -> None:
    await _send_message_event(channel, data["updated_message_id"], ChannelEventAction.UPDATED_MESSAGE)


async def _deleted_message_event(channel: Channel, data: dict[str, Any]) -> None:
    await channel.send_event(
        ChannelEventResource.CHAT_MESSAGE,
        ChannelEventAction.DELETED_MESSAGE,
        id=str(data["deleted_message_id"]),
    )


@handle_stream("chats_index")
async def handle_chats_index_json_events(channel: Channel, **data):
    pagination = await Pagination.create(Chat, queryset=_user_chats_queryset(channel.current_user))

    chat_ids = [chat.id for chat in pagination.results]
    mailbox_entries = await _fetch_mailbox_entries(channel.current_user.id, chat_ids)

    chats = [
        _chat_list_item_response(chat, channel.current_user.id, mailbox_entries.get(chat.id))
        for chat in pagination.results
    ]

    chats_data = [c.model_dump(mode="json") for c in chats]

    await channel.send_event(
        ChannelEventResource.CHATS_INDEX,
        ChannelEventAction.UPDATED,
        chats=chats_data,
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


# Order matters — first matching key wins, preserving prior if/elif behavior
_CHAT_EVENT_HANDLERS: tuple[tuple[str, Callable[[Channel, dict[str, Any]], Awaitable[None]]], ...] = (
    ("typing_user_ids", _typing_event),
    ("collaborator_added", _collaborator_added_event),
    ("collaborator_removed", _collaborator_removed_event),
    ("chat_archived", _chat_archived_event),
    ("new_message_id", _new_message_event),
    ("updated_message_id", _updated_message_event),
    ("deleted_message_id", _deleted_message_event),
)


@handle_stream("chat")
async def handle_chat_json_events(channel: Channel, **data: Any):
    for key, handler in _CHAT_EVENT_HANDLERS:
        if key in data:
            await handler(channel, data)
            return
