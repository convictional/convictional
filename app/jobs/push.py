import asyncio
import json
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from uuid import UUID

from app.models.accounts import PushSubscription, User
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import (
    MENTION_PATTERN,
    Event,
    Mention,
    Notification,
    Workspace,
    WorkspaceMixin,
)
from app.models.workspaces.chat import Chat, ChatMessage
from config import settings
from config.enums import EventAction, JobQueue
from infra.db import GlobalID
from infra.jobs import JobDefinition
from infra.push import send_push
from lib.markdown import markdown_to_plain_text
from lib.strings import truncate

# 50 chars (ellipsis included on overflow) renders cleanly on narrow lock
# screens without OS-level mid-word truncation.
_TITLE_CHAR_LIMIT = 50
_PREVIEW_CHAR_LIMIT = 140
# Web Push payloads max at ~4KB over the wire (FCM/Mozilla); after RFC 8291
# encryption overhead, ~3KB of usable bytes remain. A 2KB cap on the JSON form
# leaves margin and trips loudly if a future field pushes the budget.
_PAYLOAD_BYTE_LIMIT = 2048


class PushDeliveryRetryableError(Exception):
    pass


async def _load_push_context(
    workspace: Workspace, *, owner_id: UUID
) -> tuple[WorkspaceMixin | None, MailboxEntry | None]:
    """Load the resource and the owner's mailbox entry for a push payload.

    fetch_resource_or_none reassigns resource.workspace to the workspace we
    already hold, so a resource-side collaborator prefetch wouldn't propagate —
    load collaborators on the workspace directly (resolved_title reads them for
    untitled chats). Returns (None, ...) when the resource is gone/soft-deleted;
    callers bail on that.
    """
    resource, mailbox_entry, _ = await asyncio.gather(
        workspace.fetch_resource_or_none(),
        MailboxEntry.get_or_none(owner_id=owner_id, resource_gid=str(workspace.resource_gid)),
        workspace.fetch_related("collaborators__user"),
    )
    return resource, mailbox_entry


class SendMentionPushJob(JobDefinition):
    default_queue = JobQueue.PUSH
    mention_id: UUID

    async def perform(self):
        # The Notifier short-circuits at enqueue, but jobs already in flight when the flag
        # flipped still need a guard.
        if not settings.push_enabled:
            return

        mention = await Mention.get_or_none(id=self.mention_id).prefetch_related("workspace", "mentioned", "creator")
        # event_id is nullable (ON DELETE SET NULL on the FK) — without the event there's
        # no per-event ledger key to write against. User uses an unscoped Manager, so a
        # soft-deleted recipient still resolves; suppress push for them explicitly.
        if not mention or mention.event_id is None or mention.mentioned.is_deleted:
            return

        if not mention.mentioned.is_in_working_hours(mention.created_at):
            return

        subscriptions = await PushSubscription.filter(user_id=mention.mentioned_id).all()
        if not subscriptions:
            return

        # Mentions push for chats and posts (per notify_mention_push), so resolve
        # the resource generically rather than assuming a Chat.
        resource, mailbox_entry = await _load_push_context(mention.workspace, owner_id=mention.mentioned_id)
        if resource is None:
            return

        payload = self._build_payload(mention=mention, resource=resource, mailbox_entry=mailbox_entry)

        retryable_flags = await asyncio.gather(
            *[
                _deliver_to_device(
                    event_id=mention.event_id,
                    user_id=mention.mentioned_id,
                    subscription=subscription,
                    payload=payload,
                )
                for subscription in subscriptions
            ]
        )
        if any(retryable_flags):
            # On retry, already-delivered devices short-circuit above; only failed devices retry.
            raise PushDeliveryRetryableError("at least one device hit a retryable error")

    @staticmethod
    def _build_payload(*, mention: Mention, resource: WorkspaceMixin, mailbox_entry: MailboxEntry | None) -> dict:
        resource_gid = mention.workspace.resource_gid
        url_path = _resource_url_path(resource_gid)
        mailbox_entry_url_path = _mailbox_entry_url_path(resource_gid, mailbox_entry) if mailbox_entry else None
        title = _resource_title(resource=resource, viewer_id=mention.mentioned_id)
        body = f"{mention.creator.display_name} mentioned you: {_message_preview(mention.content)}"
        tag = f"mention-{mention.id}"
        return _finalize_payload(
            build_payload(
                title=title,
                body=body,
                url_path=url_path,
                mailbox_entry_url_path=mailbox_entry_url_path,
                tag=tag,
            )
        )


class SendEventPushJob(JobDefinition):
    default_queue = JobQueue.PUSH
    event_id: UUID
    recipient_id: UUID

    async def perform(self):
        if not settings.push_enabled:
            return

        event, recipient, subscriptions = await asyncio.gather(
            Event.get_or_none(id=self.event_id).prefetch_related("creator", "workspace"),
            User.get_or_none(id=self.recipient_id),
            PushSubscription.filter(user_id=self.recipient_id).all(),
        )
        if not event or not recipient or recipient.is_deleted or not subscriptions:
            return
        if not recipient.is_in_working_hours(event.created_at):
            return

        resource, mailbox_entry = await _load_push_context(event.workspace, owner_id=recipient.id)
        if resource is None:
            return

        payload = await _build_event_payload(
            event=event, resource=resource, user_id=recipient.id, mailbox_entry=mailbox_entry
        )

        retryable_flags = await asyncio.gather(
            *[
                _deliver_to_device(
                    event_id=event.id,
                    user_id=recipient.id,
                    subscription=subscription,
                    payload=payload,
                )
                for subscription in subscriptions
            ]
        )
        if any(retryable_flags):
            raise PushDeliveryRetryableError("at least one device hit a retryable error")


async def _deliver_to_device(*, event_id: UUID, user_id: UUID, subscription: PushSubscription, payload: dict) -> bool:
    """Return True iff the relay reported a transient failure (caller raises to retry)."""
    ledger = await Notification.push_record_for(event_id=event_id, user_id=user_id, subscription=subscription)
    if ledger.delivered_at:
        return False

    outcome = await send_push(
        endpoint=subscription.endpoint,
        protocol=subscription.protocol,
        p256dh_key=subscription.p256dh_key,
        auth_key=subscription.auth_key,
        payload=payload,
        subscription_id=subscription.id,
    )
    if outcome.success:
        await ledger.mark_delivered_to(subscription)
        return False
    if outcome.subscription_invalidated:
        # The device is permanently gone, not lagging — no retry.
        await subscription.soft_delete()
        return False
    return outcome.retryable


# Generic action labels per event type. The title slot already names the resource
# ("Q3 plan", "Project Team"), so the action verb stays bare — no "on a post" suffix.
# Anything not listed falls back to "shared an update".
#
# POST_ANNOUNCED is absent on purpose: an announcement broadcast reaches the whole org
# through the inbox (resolve_for_inbox force-include) but never pushes — posts don't move
# at chat pace, so an org-wide blast shouldn't buzz everyone's device. An @mention inside
# an announcement still pushes, but through the mention path (which builds its own
# "mentioned you" payload), not this label table.
_ACTION_LABELS: dict[EventAction, str] = {
    EventAction.CHAT_MESSAGE_CREATED: "sent a message",
    EventAction.COMMENTED: "commented",
    # Only the assignee is pushed for an assignment (see resolve_for_push), so "you" is correct.
    EventAction.ASSIGNED: "assigned this to you",
    EventAction.DECIDED: "made a decision",
    EventAction.POST_COMMENTED: "commented",
    EventAction.POST_CREATED: "posted",
    EventAction.POST_DECIDED: "made a decision",
    EventAction.GOAL_COMMENTED: "commented",
    EventAction.GOAL_UPDATED: "updated the goal",
    EventAction.GOAL_UPDATE_POSTED: "posted an update",
    EventAction.DOCUMENT_COMMENTED: "commented",
    EventAction.MEETING_UPDATED: "updated the meeting",
    EventAction.MEETING_AGENDA_UPDATED: "updated the agenda",
}


async def _build_event_payload(
    *, event: Event, resource: WorkspaceMixin, user_id: UUID, mailbox_entry: MailboxEntry | None
) -> dict:
    resource_gid = event.workspace.resource_gid
    url_path = _resource_url_path(resource_gid)
    mailbox_entry_url_path = _mailbox_entry_url_path(resource_gid, mailbox_entry) if mailbox_entry else None
    title = _resource_title(resource=resource, viewer_id=user_id)
    body = await _event_body(event=event, resource=resource)
    tag = f"event-{event.id}"
    return _finalize_payload(
        build_payload(
            title=title,
            body=body,
            url_path=url_path,
            mailbox_entry_url_path=mailbox_entry_url_path,
            tag=tag,
        )
    )


def build_payload(
    *,
    title: str,
    body: str,
    url_path: str,
    mailbox_entry_url_path: str | None = None,
    tag: str | None = None,
) -> dict:
    """Construct the JSON the service worker receives in the push event.

    `url`/`url_path` is the bare resource URL — absolute (for `clients.openWindow`)
    and pathname (for `clients.matchAll` comparison) forms. `mailbox_entry_url`/
    `mailbox_entry_url_path` mirror that pair for the mailbox-entry tap target
    and are omitted when the recipient has no entry. The SW prefers the
    mailbox-entry URL for the tap (so opening auto-marks the entry read) and
    checks focus against either path.
    """
    payload: dict = {
        "title": title,
        "body": body,
        "url": _absolute_url(url_path),
        "url_path": url_path,
        "tag": tag,
    }
    if mailbox_entry_url_path is not None:
        payload["mailbox_entry_url"] = _absolute_url(mailbox_entry_url_path)
        payload["mailbox_entry_url_path"] = mailbox_entry_url_path
    return payload


def _absolute_url(path: str) -> str:
    return urljoin(str(settings.base_url), path)


def _resource_url_path(resource_gid: GlobalID) -> str:
    # GlobalID.to_url is the canonical URL for a resource; urlunparse rebuilds it
    # as a path-only string while preserving any fragment/query GlobalID adds
    # (the gid redirect already uses fragments for GoalComment), so string concat
    # would silently drop them.
    parsed = urlparse(resource_gid.to_url)
    return urlunparse(("", "", parsed.path, parsed.params, parsed.query, parsed.fragment))


def _mailbox_entry_url_path(resource_gid: GlobalID, mailbox_entry: MailboxEntry) -> str:
    # Appending mailbox_entry_id to the resource URL is what the gid_redirect
    # endpoint passes through to the resource page so it can auto-mark the
    # entry read on open. urlencode covers the escape even though UUIDs don't
    # currently need it.
    parsed = urlparse(resource_gid.to_url)
    query_params = parse_qsl(parsed.query)
    query_params.append(("mailbox_entry_id", str(mailbox_entry.id)))
    return urlunparse(("", "", parsed.path, parsed.params, urlencode(query_params), parsed.fragment))


def _finalize_payload(payload: dict) -> dict:
    # body is the only field with user-controlled length; the rest are bounded by
    # ID/title shape. Truncate the body if we somehow exceed the budget so the relay
    # doesn't reject the whole push for a single long message.
    if len(json.dumps(payload).encode("utf-8")) > _PAYLOAD_BYTE_LIMIT:
        payload["body"] = truncate(payload["body"], _PREVIEW_CHAR_LIMIT)
    return payload


def _resource_title(*, resource: WorkspaceMixin, viewer_id: UUID) -> str:
    if isinstance(resource, Chat):
        return truncate(resource.resolved_title(viewer_id=viewer_id), _TITLE_CHAR_LIMIT)
    return truncate(resource.title or "Activity", _TITLE_CHAR_LIMIT)


async def _event_body(*, event: Event, resource: WorkspaceMixin) -> str:
    creator_name = event.creator.display_name if event.creator else "Someone"
    action_label = _ACTION_LABELS.get(event.action, "shared an update")

    if event.action == EventAction.CHAT_MESSAGE_CREATED and isinstance(resource, Chat):
        message = await ChatMessage.get_or_none(id=event.recordable_id)
        preview = _message_preview(message.content if message else None)
        if preview:
            return f"{creator_name}: {preview}"
    return f"{creator_name} {action_label}"


def _message_preview(content: str | None) -> str:
    if not content:
        return ""
    # @[Name] mention markers are noise in the preview — show "Name" instead.
    text = re.sub(MENTION_PATTERN, r"\1", content)
    return truncate(markdown_to_plain_text(text), _PREVIEW_CHAR_LIMIT)
