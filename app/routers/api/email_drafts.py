import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from tortoise import BaseDBAsyncClient

from app.helpers.datetimes import default_snooze_times
from app.helpers.email import build_body_content
from app.helpers.users import user_avatar_url
from app.jobs.content import ContentIndexingJob
from app.jobs.email import ScheduledDraftSendJob
from app.jobs.notifications import Notifier
from app.models.accounts import User
from app.models.collaboration.mailbox import Mailbox
from app.models.workspaces.email.thread import EmailDraft, EmailMessage, EmailThread, SendSideEffectOptions
from app.presenters.email_threads import EmailThreadPresenter
from app.routers.api.schemas import (
    ComposerResponse,
    ComposerSnoozePreset,
    DraftComposeRequest,
    DraftEnvelopeResponse,
    DraftEnvelopeUpdateRequest,
    DraftScheduleRequest,
    DraftScheduleResponse,
    DraftSendRequest,
    UserResponse,
)
from app.routers.api.serializers import attachment_response
from app.routers.api.streams import register_live_document_handler
from app.routers.dependencies import (
    Channel,
    Helpers,
    get_current_user,
    get_draft_for_channel,
    get_email_draft,
    get_email_draft_for_deletion,
    get_helpers,
    handle_stream,
)
from app.routers.email_threads import get_email_thread
from config.enums import ChannelEventAction, ChannelEventResource, EmailDraftAction, EmailMessageType, EventAction
from infra.db import transaction
from infra.email import EmailClient, get_email_client
from infra.jobs import Job, cancel_job, enqueue_job

router = APIRouter(tags=["inbox"])


#
# Helpers
#


def composer_response(
    draft: EmailDraft,
    thread: EmailThread,
    current_user: User,
    helpers: Helpers,
) -> ComposerResponse:
    """Wire-format response for the React EmailComposer island.

    Single source of truth for the composer's initial state. Templates emit
    only the bootstrap shape `{threadId, focusBody}` in `data-props`; the
    island fetches this endpoint on mount.
    """
    other_collaborators = [c for c in thread.workspace.collaborators if c.user_id != thread.creator_id]
    draft_url = str(helpers.url_for("api_email_drafts_show", email_thread_id=thread.id))
    attachments_base_url = str(helpers.url_for("api_email_attachments_index", email_thread_id=thread.id))
    return ComposerResponse(
        thread_id=str(thread.id),
        draft_message_id=str(draft.message.id),
        current_user=UserResponse(
            id=str(current_user.id),
            display_name=current_user.display_name,
            picture=user_avatar_url(current_user),
        ),
        upload_url=str(helpers.url_for("api_email_attachments_create", email_thread_id=thread.id)),
        # GET lists attachments; DELETE on `{attachments_base_url}/{id}` removes one.
        attachments_base_url=attachments_base_url,
        patch_url=draft_url,
        send_url=str(helpers.url_for("api_email_drafts_send", email_thread_id=thread.id)),
        schedule_url=str(helpers.url_for("api_email_drafts_schedule", email_thread_id=thread.id)),
        unschedule_url=str(helpers.url_for("api_email_drafts_unschedule", email_thread_id=thread.id)),
        delete_url=draft_url,
        draft_url=draft_url,
        initial_envelope=_envelope_response(draft, thread, current_user, helpers),
        is_shared_draft=len(other_collaborators) > 0,
        mailbox_index_url=str(helpers.url_for("mailbox_index")),
        default_snooze_times=[ComposerSnoozePreset(**preset) for preset in default_snooze_times(helpers.timezone)],
    )


def _envelope_response(
    draft: EmailDraft, thread: EmailThread, current_user: User, helpers: Helpers
) -> DraftEnvelopeResponse:
    presenter = EmailThreadPresenter(thread, current_user=current_user)
    can_reply = thread.can_reply(current_user)
    cannot_send_reason = None if can_reply else presenter.send_button_tooltip
    attachments = [attachment_response(a, helpers) for a in draft.message.attachments]
    return DraftEnvelopeResponse(
        to=draft.message.to or [],
        cc=draft.message.cc or [],
        bcc=draft.message.bcc or [],
        subject=draft.message.subject or "",
        in_reply_to_id=str(draft.message.in_reply_to_id) if draft.message.in_reply_to_id else None,
        attachments=attachments,
        sendable_by=presenter.sendable_by,
        can_reply=can_reply,
        cannot_send_reason=cannot_send_reason,
        is_scheduled=draft.message.is_scheduled,
        scheduled_for=draft.message.scheduled_for,
        body_html=draft.message.body_html,
    )


async def _apply_envelope_and_build_body(email_draft: EmailDraft, body: DraftComposeRequest) -> dict:
    """Apply the request envelope to the draft and render its body content.

    Shared by the send and schedule endpoints. build_body_content (nh3 sanitize) is CPU-bound and
    pure/no-DB; run it off the event loop and before opening the transaction so the row lock isn't
    held across this work.
    """
    email_draft.apply_envelope(body.subject, body.to, body.cc, body.bcc)
    return await asyncio.to_thread(build_body_content, body.message_body)


async def _persist_body_and_validate(
    email_draft: EmailDraft, body_content: dict, connection: BaseDBAsyncClient
) -> None:
    """Persist the envelope, set the rendered body, and reject an unsendable draft with 422.

    The body fields are set in memory; the caller's transition save (mark_draft_sending /
    mark_draft_scheduled) persists them.
    """
    await email_draft.save(using_db=connection)

    email_draft.set_rendered_body(body_content)

    validation_errors = email_draft.validate_for_sending()
    if validation_errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=validation_errors)


#
# HTTP endpoints
#


@router.get("/email_threads/{email_thread_id}/draft", response_model=DraftEnvelopeResponse)
async def api_email_drafts_show(
    thread: EmailThread = Depends(get_email_thread),
    email_draft: EmailDraft = Depends(get_email_draft),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    return _envelope_response(email_draft, thread, current_user, helpers)


@router.get("/email_threads/{email_thread_id}/composer", response_model=ComposerResponse)
async def api_email_drafts_composer(
    thread: EmailThread = Depends(get_email_thread),
    email_draft: EmailDraft = Depends(get_email_draft),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    # The React reply composer fetches this on mount. The TypeScript prop
    # shape (EmailComposerProps) is the consumer contract — keep the response
    # in lock step.
    return composer_response(email_draft, thread, current_user, helpers)


@router.patch("/email_threads/{email_thread_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
async def api_email_drafts_update(
    body: DraftEnvelopeUpdateRequest,
    thread: EmailThread = Depends(get_email_thread),
    email_draft: EmailDraft = Depends(get_email_draft),
    current_user: User = Depends(get_current_user),
):
    if email_draft.message.message_type == EmailMessageType.SENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cannot edit draft that is currently being sent"
        )

    if email_draft.message.is_scheduled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cannot edit a scheduled draft; unschedule it first"
        )

    # A missing key in the JSON body means "do not touch this column." This keeps
    # two collaborators writing disjoint fields concurrently from clobbering each
    # other. The model_validator on DraftEnvelopeUpdateRequest rejects an empty
    # body with 422 before we get here.
    payload = body.model_dump(exclude_unset=True)
    update_fields: set[str] = set()
    for field_name in ("to", "cc", "bcc", "subject"):
        if field_name in payload:
            setattr(email_draft.message, field_name, payload[field_name])
            update_fields.add(field_name)

    await thread.save_draft(email_draft, current_user, update_fields=update_fields)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/email_threads/{email_thread_id}/draft/send", status_code=status.HTTP_204_NO_CONTENT)
async def api_email_drafts_send(
    body: DraftSendRequest,
    thread: EmailThread = Depends(get_email_thread),
    email_draft: EmailDraft = Depends(get_email_draft),
    email_client: EmailClient = Depends(get_email_client),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    if not thread.can_reply(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to send this draft"
        )

    send_options = SendSideEffectOptions(
        should_archive=body.should_archive,
        should_snooze=body.should_snooze,
        snoozed_until=body.snoozed_until,
    )
    option_errors = send_options.validate(datetime.now(UTC))
    if option_errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=option_errors)

    body_content = await _apply_envelope_and_build_body(email_draft, body)

    async with transaction() as connection:
        # Two collaborators clicking Send on the same shared draft race each other: both load
        # the draft as DRAFT, both reach this handler. The row lock serializes them — the loser
        # blocks until the winner commits SENDING, then sees the new state and bails before
        # enqueueing a duplicate SendEmailThroughGmailJob and ContentIndexingJob.
        locked_message = await EmailMessage.select_for_update().using_db(connection).get(id=email_draft.message.id)
        if locked_message.message_type != EmailMessageType.DRAFT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This draft has already been sent")
        if locked_message.is_scheduled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="This draft is scheduled; unschedule it before sending"
            )

        await _persist_body_and_validate(email_draft, body_content, connection)

        await thread.send_draft(email_draft, current_user, send_options, email_client, using_db=connection)

    await enqueue_job(ContentIndexingJob.from_model(thread.organization_id, thread))

    # The client advances to the next mailbox entry itself (or falls back to the
    # inbox); the flash still renders on whichever page that navigation lands on.
    helpers.flash("Message sent")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/email_threads/{email_thread_id}/draft/schedule",
    response_model=DraftScheduleResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def api_email_drafts_schedule(
    body: DraftScheduleRequest,
    thread: EmailThread = Depends(get_email_thread),
    email_draft: EmailDraft = Depends(get_email_draft),
    current_user: User = Depends(get_current_user),
):
    if not thread.can_reply(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to send this draft"
        )

    scheduled_for = body.scheduled_for.astimezone(UTC)
    schedule_errors = email_draft.validate_schedulable(scheduled_for)
    if schedule_errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=schedule_errors)

    body_content = await _apply_envelope_and_build_body(email_draft, body)

    async with transaction() as connection:
        locked_message = await EmailMessage.select_for_update().using_db(connection).get(id=email_draft.message.id)
        if locked_message.message_type != EmailMessageType.DRAFT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This draft has already been sent")
        if locked_message.is_scheduled:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This draft is already scheduled")

        await _persist_body_and_validate(email_draft, body_content, connection)

        job = await enqueue_job(
            ScheduledDraftSendJob(
                email_thread_id=email_draft.thread_id,
                message_id=email_draft.message.id,
                sender_user_id=current_user.id,
                should_archive=body.should_archive,
                perform_at=scheduled_for,
            ),
            using_db=connection,
        )
        await thread.mark_draft_scheduled(email_draft, scheduled_for, job.id, current_user, using_db=connection)

        # scheduled_for lives on the message, not the row, so a plain sync sees no column change.
        # Record a workspace event instead: the Notifier's SyncMailboxJob drives the event-based
        # inbox update, which pins last_event on the row (the list renders it as a "scheduled"
        # activity line) — a mailbox change that's a product of an event, no forced row push.
        # record_and_notify stays silent here: an email thread is EmailDelivery.SKIP (no email) and
        # DRAFT_SCHEDULED is outside its push policy (not a reply/assignee action, no force-include),
        # so it syncs the mailbox without push/email fan-out to collaborators.
        async with Notifier(thread, current_user).record_and_notify(EventAction.DRAFT_SCHEDULED, using_db=connection):
            pass

    return DraftScheduleResponse(scheduled_for=scheduled_for, body_html=email_draft.message.body_html)


@router.post("/email_threads/{email_thread_id}/draft/unschedule", response_model=DraftEnvelopeResponse)
async def api_email_drafts_unschedule(
    thread: EmailThread = Depends(get_email_thread),
    email_draft: EmailDraft = Depends(get_email_draft),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    if not thread.can_reply(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to send this draft"
        )

    async with transaction() as connection:
        locked_message = await EmailMessage.select_for_update().using_db(connection).get(id=email_draft.message.id)
        if locked_message.message_type != EmailMessageType.DRAFT or not locked_message.is_scheduled:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This draft is not scheduled")

        job_id = locked_message.scheduled_send_job_id
        await thread.mark_draft_unscheduled(email_draft, current_user, using_db=connection)

        # Symmetric with schedule: record the event so the Notifier's SyncMailboxJob re-derives the
        # row (clearing the scheduled badge and pinning the unschedule as the new last_event) without
        # a forced push. Silent for the same reasons as DRAFT_SCHEDULED above.
        async with Notifier(thread, current_user).record_and_notify(
            EventAction.DRAFT_UNSCHEDULED, using_db=connection
        ):
            pass

    # Best-effort Cloud Task cancel — the cleared scheduled_for above is authoritative, so a fire
    # that races this (or a cancel that no-ops) is handled by the job's own lock/guard.
    if job_id:
        job = await Job.get_or_none(id=job_id)
        if job:
            await cancel_job(job)

    return _envelope_response(email_draft, thread, current_user, helpers)


@router.delete("/email_threads/{email_thread_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
async def api_email_drafts_delete(
    email_draft: EmailDraft = Depends(get_email_draft_for_deletion),
    current_user: User = Depends(get_current_user),
):
    # Cancel a pending scheduled send so no orphan Cloud Task fires. Best-effort: the fire job
    # already no-ops on a deleted/unscheduled message, so this only avoids a wasted dispatch.
    scheduled_send_job_id = email_draft.message.scheduled_send_job_id

    async with transaction() as connection:
        thread_deleted = await email_draft.thread.remove_draft(current_user, draft=email_draft, using_db=connection)

    if scheduled_send_job_id:
        job = await Job.get_or_none(id=scheduled_send_job_id)
        if job:
            await cancel_job(job)

    if not thread_deleted:
        await Mailbox.sync(email_draft.thread)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


#
# Channels
#
# Channel handler for the email_thread_draft broadcast.
# Emits structured JSON events to React subscribers.
#


@handle_stream("email_thread_draft")
async def email_draft_json_broadcast(channel: Channel, **data) -> None:
    action = data.get("action")
    actor_id = data.get("user_id", "")
    thread_id = channel.get_param("thread_id")
    if isinstance(thread_id, str):
        thread_id = UUID(thread_id)
    if not channel.current_user or thread_id is None:
        return

    match action:
        case EmailDraftAction.DRAFT_STARTED:
            if channel.current_user.id == actor_id:
                return
            draft = await get_draft_for_channel(thread_id, channel.current_user)
            if not draft:
                return
            await channel.send_event(
                ChannelEventResource.EMAIL_DRAFT,
                ChannelEventAction.DRAFT_STARTED,
                user_id=str(actor_id),
                thread_id=str(thread_id),
                draft_message_id=str(draft.message.id),
            )

        case EmailDraftAction.DRAFT_UPDATED:
            # No sender skip — every collaborator (including the actor's other sessions) needs server-truth envelope.
            draft = await get_draft_for_channel(thread_id, channel.current_user)
            if not draft:
                return
            await channel.send_event(
                ChannelEventResource.EMAIL_DRAFT,
                ChannelEventAction.DRAFT_UPDATED,
                user_id=str(actor_id),
                envelope=_envelope_broadcast_payload(draft),
            )

        case EmailDraftAction.ASSIGNMENT_CHANGED:
            # No sender skip — every collaborator (including the actor) needs server-truth pill.
            draft = await get_draft_for_channel(thread_id, channel.current_user)
            if not draft:
                return
            presenter = EmailThreadPresenter(draft.thread, current_user=channel.current_user)
            can_reply = draft.thread.can_reply(channel.current_user)
            await channel.send_event(
                ChannelEventResource.EMAIL_DRAFT,
                ChannelEventAction.ASSIGNMENT_CHANGED,
                sendable_by=presenter.sendable_by,
                can_reply=can_reply,
                cannot_send_reason=None if can_reply else presenter.send_button_tooltip,
            )

        case EmailDraftAction.DRAFT_REMOVED:
            # No sender skip — every collaborator (including the actor's other sessions)
            # needs to tear down the composer.
            await channel.send_event(
                ChannelEventResource.EMAIL_DRAFT,
                ChannelEventAction.DRAFT_REMOVED,
                user_id=str(actor_id),
            )

        case EmailDraftAction.DRAFT_SCHEDULED:
            # No sender skip — every collaborator's composer flips to read-only scheduled state.
            draft = await get_draft_for_channel(thread_id, channel.current_user)
            if not draft:
                return
            scheduled_for = draft.message.scheduled_for
            await channel.send_event(
                ChannelEventResource.EMAIL_DRAFT,
                ChannelEventAction.DRAFT_SCHEDULED,
                user_id=str(actor_id),
                scheduled_for=scheduled_for.isoformat() if scheduled_for else None,
            )

        case EmailDraftAction.DRAFT_UNSCHEDULED:
            # No sender skip — every collaborator's composer returns to an editable draft.
            await channel.send_event(
                ChannelEventResource.EMAIL_DRAFT,
                ChannelEventAction.DRAFT_UNSCHEDULED,
                user_id=str(actor_id),
            )


def _envelope_broadcast_payload(draft: EmailDraft) -> dict:
    return {
        "to": draft.message.to or [],
        "cc": draft.message.cc or [],
        "bcc": draft.message.bcc or [],
        "subject": draft.message.subject or "",
        "in_reply_to_id": str(draft.message.in_reply_to_id) if draft.message.in_reply_to_id else None,
    }


# Handle this surface's raw live-document (Yjs) broadcasts. This is separate from
# the structured `email_thread_draft` JSON events above.
register_live_document_handler("email_draft")
