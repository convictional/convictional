import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from tortoise.backends.base.client import BaseDBAsyncClient

from app.helpers.url import convert_cid_urls_to_attachment_downloads
from app.jobs.content import ContentIndexingJob
from app.models.accounts import User
from app.models.collaboration.content import Content
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.workspaces.email.thread import (
    EmailAttachment,
    EmailDraft,
    EmailMessage,
    EmailReply,
    EmailThread,
    EmailThreadComment,
)
from app.presenters.activity import EventPresenter
from app.presenters.email_threads import EmailThreadPresenter, EventTimelineItem, MessageTimelineItem
from app.routers.api.email_thread_comments import reply_to_prefetch, serialize_email_thread_comments
from app.routers.api.schemas import (
    EmailMessageAttachmentResponse,
    EmailMessageContentItem,
    EmailMessageContentListResponse,
    EmailMessageContentResponse,
    EmailMessageHeaderResponse,
    EmailMessageResponse,
    EmailMessageSummaryResponse,
    EmailThreadCommentResponse,
    EmailThreadCreatorResponse,
    EmailThreadDetailResponse,
    EmailThreadDraftResponse,
    EmailThreadEventAssignmentDetails,
    EmailThreadEventCollaboratorDetails,
    EmailThreadEventDetails,
    EmailThreadEventResponse,
    EmailThreadMailboxEntryResponse,
    EmailThreadShowResponse,
    EmailThreadTimelineItemResponse,
)
from app.routers.api.serializers import user_response
from app.routers.dependencies import Channel, Helpers, get_current_user, get_helpers, get_mailbox, handle_stream
from app.routers.email_threads import get_email_message, get_email_thread
from config.enums import ChannelEventAction, ChannelEventResource, EmailMessageType, EmailReplyType, EventAction
from infra.db import transaction
from infra.jobs import enqueue_job
from lib.html import sanitize_email_html_content
from lib.mime_types import is_browser_supported_image
from lib.uuid import parse_uuid

router = APIRouter(tags=["inbox"])


class NewEmailThreadResponse(BaseModel):
    thread_id: str


class ReplyRequest(BaseModel):
    reply_type: EmailReplyType = EmailReplyType.REPLY
    replace_existing: bool = False


class ForwardRequest(BaseModel):
    replace_existing: bool = False


class NewDraftResponse(BaseModel):
    draft_message_id: str


class ExistingDraftConflictResponse(BaseModel):
    existing_draft: bool = True


@router.post("/email_threads", response_model=NewEmailThreadResponse, status_code=status.HTTP_201_CREATED)
async def api_email_threads_create(current_user: User = Depends(get_current_user)):
    async with transaction() as connection:
        thread, _ = await EmailThread.get_or_create_for_draft(
            draft_data={
                "user_id": current_user.id,
                "organization_id": current_user.organization_id,
                "subject": "",
                "to": [],
                "cc": [],
                "bcc": [],
            },
            using_db=connection,
        )
        email_draft = await thread.start_draft(user=current_user, using_db=connection)
        await LiveDocument.set_initial_content(email_draft.live_document_topic, "", using_db=connection)

    await Mailbox.sync(thread)

    return NewEmailThreadResponse(thread_id=str(thread.id))


@router.post(
    "/email_threads/{email_thread_id}/email_messages/{email_message_id}/reply",
    response_model=NewDraftResponse,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"model": ExistingDraftConflictResponse}},
)
async def api_email_threads_reply(
    body: ReplyRequest = ReplyRequest(),
    thread: EmailThread = Depends(get_email_thread),
    message: EmailMessage = Depends(get_email_message),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    if conflict := await _existing_draft_conflict(thread, body.replace_existing):
        return conflict

    sender_user = thread.draft_owner_for(current_user)

    async with transaction() as connection:
        reply = EmailReply(in_reply_to=message, replier=sender_user, reply_type=body.reply_type)
        initial_content = helpers.render_to_string(
            "email_threads/_reply.md.jinja", in_reply_to=message, reply_type=body.reply_type
        )
        email_draft = await _create_draft_with_content(
            thread=thread,
            sender_user=sender_user,
            subject=reply.subject,
            to=reply.to,
            cc=reply.cc,
            in_reply_to=message,
            initial_content=initial_content,
            connection=connection,
        )

    await LiveDocument.set_initial_content(email_draft.live_document_topic, initial_content)
    await thread.broadcast_draft_started(current_user)

    return NewDraftResponse(draft_message_id=str(email_draft.message.id))


@router.post(
    "/email_threads/{email_thread_id}/email_messages/{email_message_id}/forward",
    response_model=NewDraftResponse,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"model": ExistingDraftConflictResponse}},
)
async def api_email_threads_forward(
    body: ForwardRequest = ForwardRequest(),
    thread: EmailThread = Depends(get_email_thread),
    message: EmailMessage = Depends(get_email_message),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    if conflict := await _existing_draft_conflict(thread, body.replace_existing):
        return conflict

    sender_user = thread.draft_owner_for(current_user)

    async with transaction() as connection:
        subject = f"Fwd: {message.normalized_subject}"
        initial_content = helpers.render_to_string("email_threads/_forward.md.jinja", in_reply_to=message)

        email_draft = await _create_draft_with_content(
            thread=thread,
            sender_user=sender_user,
            subject=subject,
            to=[],
            cc=[],
            in_reply_to=message,
            initial_content=initial_content,
            connection=connection,
        )

        await message.fetch_related("attachments__file", using_db=connection)
        for attachment in message.attachments:
            await EmailAttachment.create(
                file_id=attachment.file_id,
                email_message_id=email_draft.message.id,
                thread_id=thread.id,
                is_inline=attachment.is_inline,
                is_referenced_in_html=attachment.is_referenced_in_html,
                content_id=attachment.content_id,
                external_attachment_id=None,
                using_db=connection,
            )
        await email_draft.message.fetch_related("attachments__file", using_db=connection)

    initial_content = convert_cid_urls_to_attachment_downloads(helpers.request, initial_content, email_draft.message)
    await LiveDocument.set_initial_content(email_draft.live_document_topic, initial_content)
    await thread.broadcast_draft_started(current_user)

    return NewDraftResponse(draft_message_id=str(email_draft.message.id))


async def _existing_draft_conflict(thread: EmailThread, replace_existing: bool) -> JSONResponse | None:
    existing_draft = await thread.get_draft()
    if existing_draft and not replace_existing:
        # JSONResponse rather than HTTPException because the generic error handler stringifies
        # dict-shaped HTTPException details (see app/routers/errors.py error_handler) and the
        # React client needs the existing_draft flag in the parsed body.
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"existing_draft": True})
    return None


async def _create_draft_with_content(
    thread: EmailThread,
    sender_user: User,
    subject: str,
    to: list[str],
    cc: list[str],
    in_reply_to: EmailMessage,
    initial_content: str,
    connection: BaseDBAsyncClient,
) -> EmailDraft:
    email_draft = await thread.start_draft(
        user=sender_user,
        subject=subject,
        to=to,
        cc=cc,
        in_reply_to=in_reply_to,
        initial_content=initial_content,
        using_db=connection,
    )
    # Local hint only — the actual threadId used at send time is resolved against the sender's
    # mailbox in SendEmailThroughGmailJob.
    email_draft.message.external_thread_id = thread.external_thread_id
    await thread.create_draft(email_draft, using_db=connection)
    return email_draft


#
# Show + action endpoints (JSON peers for the React island)
#


def _message_attachment_response(
    attachment: EmailAttachment, message: EmailMessage, helpers: Helpers
) -> EmailMessageAttachmentResponse:
    download_url = str(
        helpers.url_for("email_attachments_download", email_thread_id=message.thread_id, attachment_id=attachment.id)
    )
    if attachment.is_referenced_in_html:
        show_in_list = not is_browser_supported_image(attachment.file.content_type)
    else:
        show_in_list = True
    return EmailMessageAttachmentResponse(
        id=str(attachment.id),
        filename=attachment.file.filename,
        content_type=attachment.file.content_type,
        is_inline=attachment.is_inline,
        download_url=download_url,
        show_in_list=show_in_list,
    )


async def _message_content_html(message: EmailMessage, helpers: Helpers) -> str:
    if not message.body_html:
        return ""
    # Always sanitize on display — never trust stored body_html. Authored messages are
    # sanitized once at compose (render_email_html), but that invariant does not hold for
    # every producer: Gmail sync stores authored-typed messages (SENT/DRAFT derived from
    # Gmail labels) with raw, never-sanitized HTML, so a forwarded-from-Gmail message would
    # otherwise reach the client unsanitized. Re-sanitizing here closes that hole regardless
    # of how the message was produced. The whitespace mode is chosen by type: authored content
    # we composed must keep its runs/breaks byte-faithful, so it re-runs the
    # whitespace-preserving config — idempotent on already-clean HTML, since that config skips
    # the whitespace-stripping regexes. RECEIVED is untrusted inbound HTML and runs the
    # default, whitespace-stripping config (inbound is out of scope for fidelity). Sanitizing
    # is CPU-bound (nh3 + a BeautifulSoup linkify pass) and would block the event loop, so it
    # is offloaded to a worker thread. The CID rewrite stays on the loop — it's cheap string
    # replacement and needs connection.url_for, which isn't thread-safe.
    preserve_whitespace = message.message_type != EmailMessageType.RECEIVED
    html: str = await asyncio.to_thread(sanitize_email_html_content, message.body_html, preserve_whitespace)
    return convert_cid_urls_to_attachment_downloads(helpers.connection, html, message)


def _message_summary_response(
    message: EmailMessage, thread: EmailThread, helpers: Helpers
) -> EmailMessageSummaryResponse:
    sender = message.sender_address
    content_url = str(
        helpers.url_for("api_email_message_content", email_thread_id=thread.id, email_message_id=message.id)
    )
    reply_url = str(helpers.url_for("api_email_threads_reply", email_thread_id=thread.id, email_message_id=message.id))
    forward_url = str(
        helpers.url_for("api_email_threads_forward", email_thread_id=thread.id, email_message_id=message.id)
    )
    view_original_url = str(
        helpers.url_for("email_threads_show_original", email_thread_id=thread.id, email_message_id=message.id)
    )
    return EmailMessageSummaryResponse(
        id=str(message.id),
        message_type=message.message_type.value,
        subject=message.subject,
        raw_sender=message.sender,
        sender_name=sender.name,
        sender_email=sender.email,
        to=message.to or [],
        cc=message.cc or [],
        bcc=message.bcc or [],
        preview=message.preview,
        received_at=message.received_at,
        sent_at=message.sent_at,
        created_at=message.created_at,
        external_thread_id=message.external_thread_id,
        message_id=message.message_id,
        content_url=content_url,
        reply_url=reply_url,
        forward_url=forward_url,
        view_original_url=view_original_url,
    )


async def _message_response(
    message: EmailMessage,
    thread: EmailThread,
    helpers: Helpers,
    *,
    body_html: str | None = None,
    raw_data: dict[str, Any] | None = None,
) -> EmailMessageResponse:
    summary = _message_summary_response(message, thread, helpers)
    headers = [EmailMessageHeaderResponse(name=h["name"], value=h["value"]) for h in (message.headers_list or [])]
    return EmailMessageResponse(
        **summary.model_dump(),
        content_html=await _message_content_html(message, helpers),
        body_plain=message.body_plain,
        body_html=body_html,
        headers=headers,
        raw_data=raw_data,
        attachments=[_message_attachment_response(a, message, helpers) for a in message.attachments],
    )


def _event_details(event: EventPresenter) -> EmailThreadEventDetails | None:
    raw = event.model.details or {}
    action = event.model.action

    if action in (EventAction.ASSIGNED, EventAction.UNASSIGNED):
        assignee = raw.get("assignee") or {}
        return EmailThreadEventAssignmentDetails(
            type=action,
            subject_label=assignee.get("name") or assignee.get("email") or None,
        )
    if action == EventAction.ADDED_COLLABORATOR:
        collaborator = raw.get("collaborator") or {}
        return EmailThreadEventCollaboratorDetails(
            type=action,
            subject_label=collaborator.get("name") or collaborator.get("email") or None,
            reason=raw.get("reason") or None,
        )
    return None


def _event_response(event: EventPresenter) -> EmailThreadEventResponse:
    return EmailThreadEventResponse(
        id=str(event.model.id),
        action=event.model.action.value,
        created_at=event.model.created_at,
        creator=user_response(event.creator),
        details=_event_details(event),
    )


def _timeline_item_response(
    item: MessageTimelineItem | EventTimelineItem,
    thread: EmailThread,
    helpers: Helpers,
) -> EmailThreadTimelineItemResponse | None:
    if isinstance(item, MessageTimelineItem):
        if item.item.message_type == EmailMessageType.DRAFT:
            return None
        # The timeline is a metadata-only summary: bodies are fetched on demand via
        # content_url, so the server takes no view on which messages render expanded.
        return EmailThreadTimelineItemResponse(
            type="message",
            item_id=str(item.item.id),
            created_at=item.created_at,
            message=_message_summary_response(item.item, thread, helpers),
        )
    # Comments render as native React items from EmailThreadShowResponse.comments, so the
    # "commented" activity event would double up. The Event row still exists for
    # notifications/feeds; it just doesn't belong in this timeline.
    if item.item.model.action == EventAction.COMMENTED:
        return None
    return EmailThreadTimelineItemResponse(
        type="event",
        item_id=str(item.item.model.id),
        created_at=item.created_at,
        event=_event_response(item.item),
    )


async def _comment_responses(thread: EmailThread, current_user: User) -> list[EmailThreadCommentResponse]:
    comments = (
        await EmailThreadComment.filter(email_thread_id=thread.id)
        .prefetch_related("user__avatar_file", "link_preview", await reply_to_prefetch())
        .order_by("created_at")
    )
    return await serialize_email_thread_comments(comments, current_user)


def _last_event_id(timeline: list[MessageTimelineItem | EventTimelineItem]) -> str | None:
    for item in reversed(timeline):
        if isinstance(item, EventTimelineItem):
            return str(item.item.model.id)
    return None


@router.get("/email_threads/{email_thread_id}", name="api_email_threads_show", response_model=EmailThreadShowResponse)
async def api_email_threads_show(
    thread: EmailThread = Depends(get_email_thread),
    mailbox: Mailbox = Depends(get_mailbox),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    mailbox_entry = await mailbox.entry(thread).get()
    presenter = EmailThreadPresenter(thread, current_user=current_user)
    timeline = await presenter.build_timeline()
    draft = await thread.get_draft()

    own_thread_id: str | None = None
    if mailbox_entry.is_shared:
        own_thread = await thread.find_corresponding_thread(mailbox.user.id)
        if own_thread:
            own_thread_id = str(own_thread.id)

    timeline_items = [
        item for item in (_timeline_item_response(i, thread, helpers) for i in timeline) if item is not None
    ]
    comments = await _comment_responses(thread, current_user)

    draft_response: EmailThreadDraftResponse | None = None
    if draft:
        composer_url = str(helpers.url_for("api_email_drafts_composer", email_thread_id=thread.id))
        draft_response = EmailThreadDraftResponse(
            message_id=str(draft.message.id),
            composer_url=composer_url,
        )

    return EmailThreadShowResponse(
        thread=EmailThreadDetailResponse(
            id=str(thread.id),
            title=thread.title or "",
            workspace_id=str(thread.workspace_id),
            creator=EmailThreadCreatorResponse(
                id=str(thread.creator.id),
                display_name=thread.creator.display_name,
            ),
            can_reply=thread.can_reply(current_user),
            is_shared=mailbox_entry.is_shared,
            own_thread_id=own_thread_id,
        ),
        mailbox_entry=EmailThreadMailboxEntryResponse(
            id=str(mailbox_entry.id),
            is_unread=mailbox_entry.is_unread,
            is_archived=mailbox_entry.is_archived,
            is_snoozed=mailbox_entry.is_snoozed_now,
            snoozed_until=mailbox_entry.snoozed_until,
            is_ai_excluded=mailbox_entry.is_ai_excluded,
            is_shared=mailbox_entry.is_shared,
            read_at=mailbox_entry.read_at,
        ),
        timeline=timeline_items,
        comments=comments,
        draft=draft_response,
        last_event_id=_last_event_id(timeline),
    )


@router.get(
    "/email_threads/{email_thread_id}/email_messages/{email_message_id}/content",
    name="api_email_message_content",
    response_model=EmailMessageContentResponse,
)
async def api_email_message_content(
    thread: EmailThread = Depends(get_email_thread),
    message: EmailMessage = Depends(get_email_message),
    helpers: Helpers = Depends(get_helpers),
):
    return EmailMessageContentResponse(
        content_html=await _message_content_html(message, helpers),
        body_plain=message.body_plain,
        attachments=[_message_attachment_response(a, message, helpers) for a in message.attachments],
    )


# Max message ids per batch-content request. Caps the sanitization a single request can
# drive; the client chunks its expanded-message ids into requests of this size, so a thread
# with more expanded messages makes ceil(n / cap) requests instead of one. Keep in sync with
# CONTENT_BATCH_SIZE in EmailThreadShow.tsx.
MAX_BATCH_CONTENT_IDS = 20


@router.get(
    "/email_threads/{email_thread_id}/email_message_contents",
    name="api_email_message_contents",
    response_model=EmailMessageContentListResponse,
)
async def api_email_message_contents(
    ids: list[UUID] = Query(default_factory=list, max_length=MAX_BATCH_CONTENT_IDS),
    thread: EmailThread = Depends(get_email_thread),
    helpers: Helpers = Depends(get_helpers),
):
    # Batch peer of the per-message content endpoint: the client requests the bodies of
    # the messages it renders expanded on load in one round trip instead of one per
    # message. get_email_thread already prefetches messages__attachments__file, so this
    # does no extra DB work — it only sanitizes the requested subset. Unknown or
    # cross-thread ids are simply absent from the response (the client falls back to a
    # single fetch); authorization is enforced by get_email_thread.
    requested = set(ids)
    messages = [m for m in thread.messages if m.id in requested and m.message_type != EmailMessageType.DRAFT]
    # Sanitizing is CPU-bound; _message_content_html offloads it to a worker thread, so
    # gathering keeps the event loop free while the bodies sanitize in parallel.
    htmls = await asyncio.gather(*(_message_content_html(m, helpers) for m in messages))
    contents = [
        EmailMessageContentItem(
            id=str(message.id),
            content_html=html,
            body_plain=message.body_plain,
            attachments=[_message_attachment_response(a, message, helpers) for a in message.attachments],
        )
        for message, html in zip(messages, htmls)
    ]
    return EmailMessageContentListResponse(contents=contents)


@router.get(
    "/email_threads/{email_thread_id}/email_messages/{email_message_id}",
    name="api_email_message_show",
    response_model=EmailMessageResponse,
)
async def api_email_message_show(
    thread: EmailThread = Depends(get_email_thread),
    message: EmailMessage = Depends(get_email_message),
    helpers: Helpers = Depends(get_helpers),
):
    raw_data = await message.get_raw_data()
    return await _message_response(message, thread, helpers, body_html=message.body_html, raw_data=raw_data)


async def _set_ai_exclusion(thread: EmailThread, current_user: User, is_excluded: bool) -> None:
    # The HTML endpoints flash-redirect non-creators; the JSON peer raises 403 so the
    # React client can show an inline error instead of swapping out the page.
    if thread.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the thread creator can change AI inclusion"
        )

    async with transaction() as connection:
        content = (
            await Content.filter(organization_id=thread.organization_id, source_id=str(thread.global_id))
            .using_db(connection)
            .first()
        )
        if content:
            content.is_ai_excluded = is_excluded
            await content.save(update_fields=["is_ai_excluded"], using_db=connection)
        elif not is_excluded:
            await enqueue_job(ContentIndexingJob.from_model(thread.organization_id, thread))

        await (
            MailboxEntry.filter(resource_gid=str(thread.global_id))
            .using_db(connection)
            .update(is_ai_excluded=is_excluded)
        )


@router.post(
    "/email_threads/{email_thread_id}/exclude_from_ai",
    name="api_email_threads_exclude_from_ai",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def api_email_threads_exclude_from_ai(
    thread: EmailThread = Depends(get_email_thread),
    current_user: User = Depends(get_current_user),
):
    await _set_ai_exclusion(thread, current_user, is_excluded=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/email_threads/{email_thread_id}/include_in_ai",
    name="api_email_threads_include_in_ai",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def api_email_threads_include_in_ai(
    thread: EmailThread = Depends(get_email_thread),
    current_user: User = Depends(get_current_user),
):
    await _set_ai_exclusion(thread, current_user, is_excluded=False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


#
# Channels
#
#


@handle_stream("email_thread")
async def email_thread_json_broadcast(channel: Channel, **data) -> None:
    thread_id = channel.get_param("thread_id")
    new_message_id = data.get("new_message_id")
    if not thread_id or not new_message_id:
        return

    thread_uuid = parse_uuid(str(thread_id))
    message_uuid = parse_uuid(str(new_message_id))
    if not thread_uuid or not message_uuid or not channel.current_user:
        return

    # Sender skip — the actor already has the message in their tab; broadcasting it back
    # would double-render it in the React timeline.
    if channel.current_user.id == data.get("user_id"):
        return

    thread = await EmailThread.get_or_none(id=thread_uuid).prefetch_related(
        "workspace__collaborators",
        "creator",
    )
    if not thread or not thread.collaboration.can_be_accessed_by(channel.current_user):
        return

    message = await EmailMessage.get_or_none(id=message_uuid, thread_id=thread.id)
    if not message or message.message_type == EmailMessageType.DRAFT:
        return

    await channel.send_event(
        ChannelEventResource.EMAIL_THREAD,
        ChannelEventAction.MESSAGE_ADDED,
        thread_id=str(thread.id),
        message=_message_summary_response(message, thread, channel.helpers).model_dump(mode="json"),
    )
