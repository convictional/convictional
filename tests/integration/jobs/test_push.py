import json
from datetime import UTC, datetime, time
from urllib.parse import urlparse

import pytest

from app.jobs.notifications import Notifier
from app.jobs.push import (
    PushDeliveryRetryableError,
    SendMentionPushJob,
    _message_preview,
)
from app.models.accounts import PushSubscription
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Mention, Notification
from app.models.workspaces.chat import ChatMessage
from config.enums import DeliveryChannel, EventAction, PushProtocol
from infra.db import allow_soft_deleted
from infra.jobs import InlineJobs, JobsOutbox
from infra.push import FakePushDelivery, PushSendResult
from tests.helpers.factories import (
    create_chat,
    create_collaborator,
    create_goal,
    create_organization,
    create_post,
    create_push_subscription,
    create_user,
)


async def _build_chat_with_mention(*, mentioned_name: str = "Bob Clams"):
    organization = await create_organization()
    alice = await create_user(name="Alice Clams", organization_id=organization.id)
    bob = await create_user(name=mentioned_name, organization_id=organization.id, time_zone="UTC")
    chat = await create_chat(organization_id=organization.id, title="Project Team")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    return organization, alice, bob, chat


async def _send_chat_mention(alice, bob, chat, content: str | None = None):
    # JobsOutbox dispatches queued jobs on exit (mirrors JobsMiddleware's per-HTTP-request
    # dispatch — required because the test bypasses the HTTP client).
    async with JobsOutbox():
        message = await ChatMessage.create(chat_id=chat.id, user_id=alice.id, content=content or f"@[{bob.name}] hey")
        notifier = Notifier(chat, alice)
        async with notifier.record_and_notify(EventAction.CHAT_MESSAGE_CREATED, recordable=message) as recording:
            await recording.resolve_mentions(message.content)
    return message, recording


async def _repush_at(mention: Mention, when: datetime) -> None:
    # Reset the ledger and timestamp so the gate is evaluated fresh — the prior
    # Notification row would otherwise short-circuit the rerun as already-delivered.
    await Mention.filter(id=mention.id).update(created_at=when)
    await Notification.filter(channel=DeliveryChannel.PUSH).delete()
    await SendMentionPushJob(mention_id=mention.id).perform()


@pytest.mark.asyncio
async def test_chat_mention_enqueues_push_job_only_when_subscriptions_exist(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    _, alice, bob, chat = await _build_chat_with_mention()

    # No subscriptions yet → no push job enqueued.
    background_jobs.reset()
    await _send_chat_mention(alice, bob, chat)
    assert not background_jobs.has_completed_job(SendMentionPushJob)
    assert push_delivery.sent == []

    # Add a subscription → mention now enqueues + runs the push job.
    await create_push_subscription(user_id=bob.id, platform="Chrome on macOS")
    background_jobs.reset()
    await _send_chat_mention(alice, bob, chat)
    assert background_jobs.has_completed_job(SendMentionPushJob)
    assert len(push_delivery.sent) == 1


@pytest.mark.asyncio
async def test_kill_switch_short_circuits_enqueue(background_jobs: InlineJobs, push_delivery: FakePushDelivery):
    # Intentionally does not use the push_enabled fixture — the kill-switch default is off.
    _, alice, bob, chat = await _build_chat_with_mention()
    await create_push_subscription(user_id=bob.id)

    background_jobs.reset()
    await _send_chat_mention(alice, bob, chat)

    assert not background_jobs.has_completed_job(SendMentionPushJob)
    assert push_delivery.sent == []


@pytest.mark.asyncio
async def test_async_resource_mention_does_not_enqueue_push(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """Goal / document / meeting @mentions stay inbox-only — those resources are
    async and never push (notify_mention_push is False on the base policy)."""
    organization = await create_organization()
    alice = await create_user(name="Alice Clams", organization_id=organization.id)
    bob = await create_user(name="Bob Clams", organization_id=organization.id)
    await create_push_subscription(user_id=bob.id)

    goal = await create_goal(creator_id=alice.id, organization_id=organization.id)
    await create_collaborator(workspace_id=goal.workspace_id, user_id=bob.id)
    await goal.fetch_related("workspace__collaborators__user")
    notifier = Notifier(goal, alice)

    background_jobs.reset()
    async with JobsOutbox():
        async with notifier.record_and_notify(EventAction.GOAL_COMMENTED) as recording:
            await recording.resolve_mentions("Hey @[Bob Clams]", recordable=goal)

    assert not background_jobs.has_completed_job(SendMentionPushJob)
    assert push_delivery.sent == []


@pytest.mark.asyncio
async def test_post_mention_enqueues_push_with_post_payload(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """Post @mentions push (directed at you), same as chat mentions. The
    generalized payload titles the post rather than assuming a Chat."""
    organization = await create_organization()
    alice = await create_user(name="Alice Clams", organization_id=organization.id)
    bob = await create_user(name="Bob Clams", organization_id=organization.id, time_zone="UTC")
    await create_push_subscription(user_id=bob.id)

    post = await create_post(title="Q3 Planning", creator_id=alice.id, organization_id=organization.id)
    await create_collaborator(workspace_id=post.workspace_id, user_id=bob.id)
    await post.fetch_related("workspace__collaborators__user")
    notifier = Notifier(post, alice)

    background_jobs.reset()
    async with JobsOutbox():
        async with notifier.record_and_notify(EventAction.POST_COMMENTED) as recording:
            await recording.resolve_mentions("Hey @[Bob Clams] thoughts?", recordable=post)

    assert background_jobs.has_completed_job(SendMentionPushJob)
    assert len(push_delivery.sent) == 1
    payload = push_delivery.sent[0].payload
    assert payload["title"] == "Q3 Planning"
    assert payload["body"] == "Alice Clams mentioned you: Hey Bob Clams thoughts?"
    assert payload["tag"].startswith("mention-")


@pytest.mark.asyncio
async def test_payload_and_notification_ledger_on_successful_send(push_enabled, push_delivery: FakePushDelivery):
    _, alice, bob, chat = await _build_chat_with_mention()
    subscription = await create_push_subscription(user_id=bob.id, platform="Chrome on macOS")

    await _send_chat_mention(alice, bob, chat, content=f"Hey @[{bob.name}] take a look")

    assert len(push_delivery.sent) == 1
    sent = push_delivery.sent[0]
    assert sent.endpoint == subscription.endpoint
    assert sent.p256dh_key == subscription.p256dh_key
    assert sent.auth_key == subscription.auth_key

    assert sent.payload["title"] == "Project Team"
    assert sent.payload["body"] == "Alice Clams mentioned you: Hey Bob Clams take a look"
    # The chat-message recording enqueues SyncMailboxJob, which creates the
    # recipient's MailboxEntry. The push job picks that entry up — `url_path` is the
    # bare resource URL (so the SW can suppress when a tab is focused on the
    # conversation) and `mailbox_entry_url_path` carries the mailbox_entry_id the
    # gid_redirect endpoint passes through to chats_show for auto-mark-read.
    gid_path = urlparse(chat.workspace.resource_gid.to_url).path
    assert sent.payload["url_path"] == gid_path
    assert sent.payload["mailbox_entry_url_path"].startswith(f"{gid_path}?mailbox_entry_id=")
    assert sent.payload["tag"].startswith("mention-")

    mention = await Mention.filter(workspace_id=chat.workspace_id, mentioned_id=bob.id).first()
    assert mention is not None
    ledger = await Notification.filter(
        event_id=mention.event_id,
        user_id=bob.id,
        channel=DeliveryChannel.PUSH,
        device_id=subscription.id,
    ).first()
    assert ledger is not None
    assert ledger.delivered_at is not None
    assert ledger.device_label_snapshot == "Chrome on macOS"


@pytest.mark.asyncio
async def test_payload_uses_mailbox_entry_tap_target(push_enabled, push_delivery: FakePushDelivery):
    """When a MailboxEntry exists, the payload carries a mailbox_entry_url that auto-marks-read on tap."""
    _, alice, bob, chat = await _build_chat_with_mention()
    await create_push_subscription(user_id=bob.id)

    entry = await MailboxEntry.create(
        owner_id=bob.id,
        organization_id=chat.organization_id,
        resource_gid=str(chat.global_id),
        title="Project Team",
        preview="…",
    )

    await _send_chat_mention(alice, bob, chat)

    assert len(push_delivery.sent) == 1
    payload = push_delivery.sent[0].payload
    gid_path = urlparse(chat.workspace.resource_gid.to_url).path
    assert payload["url_path"] == gid_path
    assert payload["mailbox_entry_url_path"] == f"{gid_path}?mailbox_entry_id={entry.id}"
    assert payload["mailbox_entry_url"].endswith(payload["mailbox_entry_url_path"])


@pytest.mark.asyncio
async def test_subscription_soft_deleted_on_gone_response(push_enabled, push_delivery: FakePushDelivery):
    """410 Gone (and 404) → the device is permanently dead, so soft-delete the row."""
    _, alice, bob, chat = await _build_chat_with_mention()
    subscription = await create_push_subscription(user_id=bob.id)

    push_delivery.respond_with(PushSendResult(success=False, subscription_invalidated=True))
    await _send_chat_mention(alice, bob, chat)

    assert len(push_delivery.sent) == 1
    async with allow_soft_deleted():
        refreshed = await PushSubscription.get(id=subscription.id)
    assert refreshed.is_deleted


@pytest.mark.asyncio
async def test_retryable_failure_raises(push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery):
    """Transient failures (500/network) raise so Cloud Tasks retries the whole job."""
    _, alice, bob, chat = await _build_chat_with_mention()
    await create_push_subscription(user_id=bob.id)

    push_delivery.respond_with(PushSendResult(success=False, retryable=True))
    await _send_chat_mention(alice, bob, chat)

    # InlineJobs swallows the exception into .failed.
    failures = [exc for _, exc in background_jobs.failed]
    assert any(isinstance(exc, PushDeliveryRetryableError) for exc in failures)
    ledger = await Notification.filter(channel=DeliveryChannel.PUSH).first()
    assert ledger is not None
    assert ledger.delivered_at is None

    background_jobs.failed.clear()  # the conftest teardown raises otherwise


@pytest.mark.asyncio
async def test_already_delivered_device_short_circuits_on_retry(push_enabled, push_delivery: FakePushDelivery):
    """Per-device idempotency: a second run of the same job skips already-delivered devices."""
    _, alice, bob, chat = await _build_chat_with_mention()
    await create_push_subscription(user_id=bob.id, platform="Chrome on macOS")

    _, recording = await _send_chat_mention(alice, bob, chat)
    mention = recording.mentions[0]
    assert len(push_delivery.sent) == 1

    await SendMentionPushJob(mention_id=mention.id).perform()
    assert len(push_delivery.sent) == 1


@pytest.mark.asyncio
async def test_working_hours_gate_drops_outside_window(push_enabled, push_delivery: FakePushDelivery):
    """Mentions outside the user's working hours don't push (event-timestamp-driven gate)."""
    _, alice, bob, chat = await _build_chat_with_mention()
    bob.push_working_hours_start = time(9, 0)
    bob.push_working_hours_end = time(10, 0)
    await bob.save()
    await create_push_subscription(user_id=bob.id)

    _, recording = await _send_chat_mention(alice, bob, chat)
    mention = recording.mentions[0]
    push_delivery.reset()

    await _repush_at(mention, datetime(2026, 5, 13, 2, 0, tzinfo=UTC))
    assert push_delivery.sent == []

    await _repush_at(mention, datetime(2026, 5, 13, 9, 30, tzinfo=UTC))
    assert len(push_delivery.sent) == 1


@pytest.mark.asyncio
async def test_event_timestamp_gate_tolerates_queue_lag(push_enabled, push_delivery: FakePushDelivery):
    """The gate consults mention.created_at, not now() — 10am sent → late worker still pushes."""
    _, alice, bob, chat = await _build_chat_with_mention()
    await create_push_subscription(user_id=bob.id)

    _, recording = await _send_chat_mention(alice, bob, chat)
    mention = recording.mentions[0]
    push_delivery.reset()

    await _repush_at(mention, datetime(2026, 5, 13, 10, 0, tzinfo=UTC))
    assert len(push_delivery.sent) == 1


@pytest.mark.asyncio
async def test_concurrent_jobs_dedupe_via_unique_constraint(push_enabled, push_delivery: FakePushDelivery):
    """The (event, user, channel, device) unique index means a second run is a no-op."""
    _, alice, bob, chat = await _build_chat_with_mention()
    await create_push_subscription(user_id=bob.id)

    _, recording = await _send_chat_mention(alice, bob, chat)
    mention = recording.mentions[0]
    assert len(push_delivery.sent) == 1

    await SendMentionPushJob(mention_id=mention.id).perform()
    assert len(push_delivery.sent) == 1

    ledger_count = await Notification.filter(
        event_id=mention.event_id, user_id=bob.id, channel=DeliveryChannel.PUSH
    ).count()
    assert ledger_count == 1


@pytest.mark.asyncio
async def test_is_in_working_hours_opt_in_and_event_timestamp():
    """Both columns NULL → push at any time (opt-in feature). When set, the gate
    consults the supplied `when`, not now()."""
    organization = await create_organization()

    # No working hours set — push delivers at any clock time.
    opt_out = await create_user(organization_id=organization.id, time_zone="UTC")
    assert opt_out.is_in_working_hours(datetime(2026, 5, 13, 3, 0, tzinfo=UTC)) is True
    assert opt_out.is_in_working_hours(datetime(2026, 5, 13, 23, 0, tzinfo=UTC)) is True

    # Configured window: gate consults the event timestamp, not now().
    opted_in = await create_user(
        organization_id=organization.id,
        time_zone="UTC",
        push_working_hours_start=time(8, 0),
        push_working_hours_end=time(19, 0),
    )
    assert opted_in.is_in_working_hours(datetime(2026, 5, 13, 18, 59, tzinfo=UTC)) is True
    assert opted_in.is_in_working_hours(datetime(2026, 5, 13, 19, 1, tzinfo=UTC)) is False
    assert opted_in.is_in_working_hours(datetime(2026, 5, 13, 7, 59, tzinfo=UTC)) is False


@pytest.mark.asyncio
async def test_is_in_working_hours_handles_cross_midnight_and_degenerate():
    organization = await create_organization()

    night_shift = await create_user(
        organization_id=organization.id,
        time_zone="UTC",
        push_working_hours_start=time(22, 0),
        push_working_hours_end=time(6, 0),
    )
    assert night_shift.is_in_working_hours(datetime(2026, 5, 13, 23, 0, tzinfo=UTC)) is True
    assert night_shift.is_in_working_hours(datetime(2026, 5, 13, 1, 0, tzinfo=UTC)) is True
    assert night_shift.is_in_working_hours(datetime(2026, 5, 13, 8, 0, tzinfo=UTC)) is False

    # Equal start/end — degenerate, must never push (safer than always-push).
    degenerate = await create_user(
        organization_id=organization.id,
        time_zone="UTC",
        push_working_hours_start=time(9, 0),
        push_working_hours_end=time(9, 0),
    )
    assert degenerate.is_in_working_hours(datetime(2026, 5, 13, 9, 0, tzinfo=UTC)) is False


@pytest.mark.asyncio
async def test_is_in_working_hours_invalid_timezone_falls_back_to_utc():
    organization = await create_organization()
    user = await create_user(
        organization_id=organization.id,
        time_zone="Not/A/Zone",
        push_working_hours_start=time(8, 0),
        push_working_hours_end=time(19, 0),
    )
    assert user.is_in_working_hours(datetime(2026, 5, 13, 10, 0, tzinfo=UTC)) is True
    assert user.is_in_working_hours(datetime(2026, 5, 13, 22, 0, tzinfo=UTC)) is False


def test_message_preview_strips_mention_markup_and_caps_length():
    assert _message_preview("Hey @[Bob Clams] take a look") == "Hey Bob Clams take a look"
    assert _message_preview("<p>Hello <strong>there</strong></p>") == "Hello there"
    long = "x" * 200
    assert len(_message_preview(long)) == 140
    assert _message_preview(long).endswith("…")


def test_message_preview_strips_markdown_formatting():
    # Links collapse to their visible text — no raw [text](url) on the lock screen.
    assert _message_preview("See [the doc](https://example.com)") == "See the doc"
    # Images preserve their alt text in brackets so an image-only message isn't empty.
    assert _message_preview("![a cat](https://example.com/cat.png)") == "[a cat]"
    assert _message_preview("![](https://example.com/cat.png)") == "[image]"
    # Emphasis, code, and headings strip cleanly.
    assert _message_preview("**huge** news: `ship it`") == "huge news: ship it"
    assert _message_preview("# Heading\n\nbody") == "Heading body"


@pytest.mark.asyncio
async def test_mention_payload_truncates_long_chat_title():
    _, alice, bob, _ = await _build_chat_with_mention()
    long_title = "Q3 Strategy Review: Customer Retention And Growth Initiatives"
    chat = await create_chat(organization_id=alice.organization_id, title=long_title)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await chat.fetch_related("workspace__collaborators__user")
    mention = await Mention.create(
        recordable_gid=chat.global_id,
        content=f"@[{bob.name}] heads up",
        workspace_id=chat.workspace_id,
        mentioned_id=bob.id,
        creator_id=alice.id,
    )
    await mention.fetch_related("creator", "workspace")

    payload = SendMentionPushJob._build_payload(mention=mention, resource=chat, mailbox_entry=None)
    assert payload["title"] == "Q3 Strategy Review: Customer Retention And Growth…"
    assert len(payload["title"]) <= 50


@pytest.mark.asyncio
async def test_fanout_records_apns_protocol_for_apns_rows(push_enabled, push_delivery: FakePushDelivery):
    _, alice, bob, chat = await _build_chat_with_mention()
    subscription = await create_push_subscription(
        user_id=bob.id,
        endpoint="ExponentPushToken[mobile]",
        protocol=PushProtocol.APNS,
        p256dh_key=None,
        auth_key=None,
        platform="iPhone",
    )

    await _send_chat_mention(alice, bob, chat)

    assert len(push_delivery.sent) == 1
    sent = push_delivery.sent[0]
    assert sent.endpoint == subscription.endpoint
    assert sent.protocol == PushProtocol.APNS
    assert sent.p256dh_key is None
    assert sent.auth_key is None


@pytest.mark.asyncio
async def test_fanout_delivers_to_both_web_and_apns_for_dual_subscriber(push_enabled, push_delivery: FakePushDelivery):
    _, alice, bob, chat = await _build_chat_with_mention()
    await create_push_subscription(
        user_id=bob.id,
        endpoint="https://fcm.googleapis.com/fcm/send/desktop",
        platform="Chrome on macOS",
    )
    await create_push_subscription(
        user_id=bob.id,
        endpoint="ExponentPushToken[mobile]",
        protocol=PushProtocol.APNS,
        p256dh_key=None,
        auth_key=None,
    )

    await _send_chat_mention(alice, bob, chat)

    sent_protocols = sorted(record.protocol for record in push_delivery.sent)
    assert sent_protocols == [PushProtocol.APNS, PushProtocol.WEB_PUSH]


@pytest.mark.asyncio
async def test_payload_truncates_oversized_body():
    """A 2KB cap on the serialized payload, with body as the truncation target."""
    _, alice, bob, chat = await _build_chat_with_mention()
    mention = await Mention.create(
        recordable_gid=chat.global_id,
        content="x" * 5000,
        workspace_id=chat.workspace_id,
        mentioned_id=bob.id,
        creator_id=alice.id,
    )
    await mention.fetch_related("creator", "workspace")
    await chat.fetch_related("workspace__collaborators__user")
    payload = SendMentionPushJob._build_payload(mention=mention, resource=chat, mailbox_entry=None)
    assert len(json.dumps(payload).encode("utf-8")) <= 2048
    assert payload["body"].endswith("…")
    # Without a mailbox entry, the SW falls back to url/url_path for the tap target —
    # the mailbox-entry fields must be absent so the SW's `|| urlAbsolute` works.
    assert "mailbox_entry_url" not in payload
    assert "mailbox_entry_url_path" not in payload
