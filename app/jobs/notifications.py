import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from tortoise import BaseDBAsyncClient

from app.jobs.mailbox import SyncMailboxJob
from app.jobs.push import SendEventPushJob, SendMentionPushJob
from app.mailers.notifications import EventMailer, MentionMailer
from app.models.accounts import PushSubscription, User
from app.models.collaboration.mailbox import mailbox_entry_registry
from app.models.collaboration.workspace import (
    Event,
    Mention,
    Notification,
    Recording,
    SubscriberResolver,
    WorkspaceMixin,
)
from config import settings
from config.enums import EventAction, JobQueue
from infra.db import RecordModel
from infra.jobs import JobDefinition, enqueue_job

FORCE_NOTIFY_ACTIONS = frozenset({EventAction.POST_ANNOUNCED})


@dataclass
class Notifier:
    """Records a workspace event and dispatches its downstream consequences.

    Two surfaces, one source of truth for who-cares:
      - Inbox refresh, via SyncMailboxJob (one per event). Reach comes from
        SubscriberResolver.resolve_for_inbox; the unread-vs-content-only
        decision is layered on at the mailbox boundary, so a user below ALL
        keeps their existing row state.
      - Channel fan-out, via SendEventEmailJob / SendEventPushJob /
        SendMentionJob / SendMentionPushJob. These resolve through
        SubscriberResolver.resolve_for_push / resolve_for_email (with a
        sender-skip that's correct for email and push but would be wrong for
        inbox state — which is why mailbox sync runs as its own step).

    Inbox and email follow the level the user chose in the "Notifications" bell
    (SubscriberResolver's subscription cascade): every effective subscriber is
    notified. Push is narrower — it does not notify every subscriber. Per-policy,
    it fires for chat/post @mentions, DM and multi-person direct-chat messages,
    and replies on a post you created or are assigned (see resolve_for_push and
    notify_mentions). An announcement reaches inbox/email but never pushes; only
    an @mention inside it pushes, via notify_mentions. See the React UI at
    app/javascript/react/composites/SubscriptionBell.tsx.
    """

    resource: WorkspaceMixin
    current_user: User | None = None
    recipient: User | None = None

    @asynccontextmanager
    async def record_and_notify(
        self,
        action: EventAction,
        recordable: RecordModel | None = None,
        creator_id: UUID | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ):
        if creator_id is None and self.current_user:
            creator_id = self.current_user.id

        async with self.resource.workspace.record(action, recordable, creator_id, using_db) as recording:
            yield recording
            await self.notify(recording)

    async def notify(self, recording: Recording):
        # Mailbox sync runs first as its own concern — one job per event,
        # idempotent, includes every collaborator (no sender-skip). Notification
        # fan-out (email, push) follows separately with its own sender-skip rules.
        await self._sync_mailbox(recording)

        if self.recipient:
            await self.notify_event(recording.event, self.recipient, using_db=recording.using_db)
        elif recording.event.action in FORCE_NOTIFY_ACTIONS:
            # An announcement's org-wide inbox reach comes from SyncMailboxJob -> resolve_for_inbox
            # (force-include over org accessors); it never pushes or emails. Only @mentions inside
            # it notify individually.
            await self.notify_mentions(recording.mentions, using_db=recording.using_db)
        else:
            await self.notify_subscribers(recording)
            await self.notify_mentions(recording.mentions, using_db=recording.using_db)

    async def _sync_mailbox(self, recording: Recording):
        # SEND resources (docs, meetings) surface via Notification rows,
        # not MailboxEntry — nothing to sync here.
        if type(self.resource).record_type not in mailbox_entry_registry:
            return
        await enqueue_job(
            SyncMailboxJob(event_id=recording.event.id, unique=True),
            recording.using_db,
        )

    async def notify_subscribers(self, recording: Recording):
        exclude_user_id = self.current_user.id if self.current_user else None
        # Reuse one resolver — a second instance would re-run every _load() query.
        resolver = SubscriberResolver(workspace=self.resource.workspace, using_db=recording.using_db)
        # recording.mentions is the in-memory list. The Mention rows are saved but
        # their event_id link isn't flushed until record() exits, so passing the
        # set directly is the only correct path here.
        mention_user_ids = {mention.mentioned_id for mention in recording.mentions}
        email_recipients = await resolver.resolve_for_email(
            recording.event, mention_user_ids=mention_user_ids, exclude_user_id=exclude_user_id
        )
        push_recipients = await resolver.resolve_for_push(
            recording.event, mention_user_ids=mention_user_ids, exclude_user_id=exclude_user_id
        )

        for user in email_recipients:
            await self.notify_event(recording.event, user, using_db=recording.using_db)

        await self._notify_push_subscribers(
            recording=recording,
            push_recipients=push_recipients,
        )

    async def notify_event(self, event: Event, user: User, using_db: BaseDBAsyncClient | None = None):
        # Mailbox state for SKIP resources is handled by _sync_mailbox (one job per
        # event). This method is only the email side channel for SEND resources.
        if self.resource.email_delivery.is_send:
            notification = await Notification.create(event_id=event.id, user_id=user.id, using_db=using_db)
            await enqueue_job(SendEventEmailJob(notification_id=notification.id, unique=True), using_db)

    async def _notify_push_subscribers(
        self,
        *,
        recording: Recording,
        push_recipients: list[User],
    ):
        # Push policy (level cascade, DM force-include, mention exclusion) lives
        # in SubscriberResolver.resolve_for_push. This method handles only the
        # hardware question (which recipients have a registered device) and
        # the per-user job enqueue.
        if not settings.push_enabled or not push_recipients:
            return

        pushable_user_ids = await PushSubscription.user_ids_with_subscriptions(
            [user.id for user in push_recipients], using_db=recording.using_db
        )
        await asyncio.gather(
            *[
                enqueue_job(
                    SendEventPushJob(event_id=recording.event.id, recipient_id=user.id, unique=True),
                    recording.using_db,
                )
                for user in push_recipients
                if user.id in pushable_user_ids
            ]
        )

    async def notify_mentions(self, mentions: list[Mention], using_db: BaseDBAsyncClient | None = None):
        undelivered_mentions = [mention for mention in mentions if not mention.is_delivered]
        # Whether a mention pushes is a per-resource rule (notify_mention_push):
        # chat mentions push, post/doc/goal mentions only reach the inbox. This
        # ignores WorkspaceMixin.email_delivery entirely (chats are
        # email_delivery.SKIP but should still push). Behind a kill-switch for fast revert.
        push_mentions = settings.push_enabled and self.resource.notification_policy.notify_mention_push
        pushable_user_ids: set[UUID] = set()
        if push_mentions and undelivered_mentions:
            pushable_user_ids = await PushSubscription.user_ids_with_subscriptions(
                [m.mentioned_id for m in undelivered_mentions], using_db=using_db
            )
        for mention in undelivered_mentions:
            if self.resource.email_delivery.is_send:
                await enqueue_job(SendMentionJob(mention_id=mention.id, unique=True), using_db)
            if push_mentions and mention.mentioned_id in pushable_user_ids:
                await enqueue_job(SendMentionPushJob(mention_id=mention.id, unique=True), using_db)


class SendEventEmailJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    notification_id: UUID

    async def perform(self):
        notification = await Notification.get_or_none(id=self.notification_id).prefetch_related(
            "event__creator", "event__workspace", "user__oauth_tokens"
        )
        if not notification or notification.delivered_at:
            return

        await EventMailer(notification.event, notification.user).send()
        notification.delivered_at = datetime.now(UTC)
        await notification.save()


class SendMentionJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    mention_id: UUID

    async def perform(self):
        mention = await Mention.get_or_none(id=self.mention_id).prefetch_related(
            "workspace", "mentioned__oauth_tokens", "creator"
        )
        if not mention or mention.is_delivered:
            return

        await MentionMailer(mention).send()
        await mention.mark_delivered()
