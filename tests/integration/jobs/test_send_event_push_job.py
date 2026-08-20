from datetime import UTC, datetime, time
from urllib.parse import urlparse

import pytest

from app.jobs.notifications import Notifier
from app.jobs.push import SendEventPushJob, SendMentionPushJob
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Notification, SubscriptionPreference
from app.models.workspaces.chat import Chat, ChatMessage
from app.models.workspaces.documents import Document, DocumentComment
from app.models.workspaces.goals import Goal, GoalComment
from app.models.workspaces.posts import Post
from config.enums import DeliveryChannel, EventAction, SubscriptionLevel
from infra.jobs import InlineJobs, JobsOutbox
from infra.push import FakePushDelivery
from tests.helpers.factories import (
    create_chat,
    create_collaborator,
    create_document,
    create_goal,
    create_group,
    create_organization,
    create_post,
    create_push_subscription,
    create_user,
)

# Push notifies a narrower audience than the subscription cascade behind
# inbox/email. SendEventPushJob fires for: DM messages (every participant);
# multi-person direct-chat messages (every subscriber — muting silences it);
# and replies on a post you created or are assigned. A group-backed (channel)
# chat message, a published post, a global Posts=ALL on a post, and an org-wide
# announcement broadcast all reach inbox/email without pushing. @mentions
# (including inside an announcement) go through SendMentionPushJob (see
# test_push.py), not this job.


async def _build_chat(*, dm: bool = False, num_extra: int = 0, recipient_time_zone: str = "UTC"):
    organization = await create_organization()
    alice = await create_user(name="Alice Clams", organization_id=organization.id)
    bob = await create_user(name="Bob Clams", organization_id=organization.id, time_zone=recipient_time_zone)
    chat = await create_chat(
        organization_id=organization.id,
        title=None if dm else "Project Team",
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    for index in range(num_extra):
        extra = await create_user(name=f"Extra {index}", organization_id=organization.id)
        await create_collaborator(workspace_id=chat.workspace_id, user_id=extra.id)
    return organization, alice, bob, chat


async def _send_message(alice, chat, content: str = "hey team") -> ChatMessage:
    async with JobsOutbox():
        message = await ChatMessage.create(chat_id=chat.id, user_id=alice.id, content=content)
        notifier = Notifier(chat, alice)
        async with notifier.record_and_notify(EventAction.CHAT_MESSAGE_CREATED, recordable=message):
            pass
    return message


@pytest.mark.asyncio
async def test_dm_fires_push_to_other_participant_without_explicit_subscription(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """DMs push the other participant even when they've turned the global Chat
    default down to RELEVANT_ONLY: a DM has no @mention and is rarely muted, so
    the force-include path pushes regardless of subscription level."""
    _, alice, bob, chat = await _build_chat(dm=True)
    await create_push_subscription(user_id=bob.id, platform="Chrome on macOS")
    pref = await SubscriptionPreference.get(subscriber_id=bob.id, resource_type=Chat.record_type)
    pref.default_level = SubscriptionLevel.RELEVANT_ONLY
    await pref.save()

    background_jobs.reset()
    await _send_message(alice, chat, "hey bob")

    assert background_jobs.has_completed_job(SendEventPushJob)
    assert len(push_delivery.sent) == 1
    sent = push_delivery.sent[0]
    assert sent.payload["body"] == "Alice Clams: hey bob"
    assert sent.payload["url_path"] == urlparse(chat.workspace.resource_gid.to_url).path


@pytest.mark.asyncio
async def test_dm_without_push_subscription_does_not_enqueue(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    _, alice, _, chat = await _build_chat(dm=True)

    background_jobs.reset()
    await _send_message(alice, chat)

    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert push_delivery.sent == []


@pytest.mark.asyncio
async def test_multi_person_direct_chat_message_pushes_subscribers(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """A multi-person direct chat (3+ people, no group) is a DM with more people:
    a plain message pushes its subscribers (members at the default ALL level)
    without any explicit opt-in, via notify_subscriber_push."""
    _, alice, bob, chat = await _build_chat(num_extra=1)  # alice + bob + 1 extra, no group => MULTI
    await chat.fetch_related("workspace__collaborators")
    assert chat.type.is_multi
    await create_push_subscription(user_id=bob.id)

    background_jobs.reset()
    await _send_message(alice, chat, "huddle update")

    assert background_jobs.has_completed_job(SendEventPushJob)
    pushed = {n.user_id for n in await Notification.filter(channel=DeliveryChannel.PUSH, device_id__isnull=False)}
    assert pushed == {bob.id}  # the other subscriber; alice is the sender, the extra has no device


@pytest.mark.asyncio
async def test_muted_multi_person_direct_chat_member_does_not_push(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """Muting a multi-person direct chat (bell to below ALL) drops the member out
    of its subscribers, so notify_subscriber_push no longer reaches them."""
    _, alice, bob, chat = await _build_chat(num_extra=1)  # MULTI
    await create_push_subscription(user_id=bob.id)
    await chat.fetch_related("workspace")
    await chat.workspace.unsubscribe(bob.id)  # bell-mute: level RELEVANT_ONLY

    background_jobs.reset()
    await _send_message(alice, chat, "more chatter")

    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert push_delivery.sent == []


@pytest.mark.asyncio
async def test_group_backed_chat_message_never_pushes(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """A plain (non-mention) message in a group-backed chat (a channel) never
    pushes — not even for a member subscribed at ALL. A channel message reaches
    the inbox; only direct chats and @mentions push."""
    organization = await create_organization()
    alice = await create_user(name="Alice Clams", organization_id=organization.id)
    bob = await create_user(name="Bob Clams", organization_id=organization.id, time_zone="UTC")
    group = await create_group(organization_id=organization.id)
    chat = await create_chat(organization_id=organization.id, group_id=group.id, title="Engineering")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await create_push_subscription(user_id=bob.id)
    await chat.workspace.subscribe(bob.id)  # explicit ALL — a channel still doesn't push

    background_jobs.reset()
    await _send_message(alice, chat, "channel update")

    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert push_delivery.sent == []


@pytest.mark.asyncio
async def test_goal_event_never_pushes_even_with_global_all(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """Goals are async — a comment on one never pushes, even for a recipient who
    dialed their global Goal preference up to ALL. Their inbox/email still fires."""
    organization = await create_organization()
    alice = await create_user(organization_id=organization.id)
    bob = await create_user(organization_id=organization.id, time_zone="UTC")
    await create_push_subscription(user_id=bob.id)
    await SubscriptionPreference.update_for(bob.id, {Goal.record_type: SubscriptionLevel.ALL})

    goal = await create_goal(creator_id=bob.id, organization_id=organization.id)
    await create_collaborator(workspace_id=goal.workspace_id, user_id=alice.id)
    await goal.fetch_related("workspace__collaborators__user")

    background_jobs.reset()
    async with JobsOutbox():
        notifier = Notifier(goal, alice)
        comment = GoalComment(content="What's the status?", goal_id=goal.id, user_id=alice.id)
        async with notifier.record_and_notify(recordable=comment, action=EventAction.GOAL_COMMENTED) as recording:
            recording.event.details.update({"comment_id": comment.id})
            await comment.save(recording.using_db)

    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert push_delivery.sent == []


@pytest.mark.asyncio
async def test_kill_switch_short_circuits_event_push(background_jobs: InlineJobs, push_delivery: FakePushDelivery):
    """The push_enabled kill-switch suppresses event push at enqueue (the same
    way it suppresses mention push), so no job runs and no relay sees the payload."""
    _, alice, bob, chat = await _build_chat(dm=True)
    await create_push_subscription(user_id=bob.id)

    background_jobs.reset()
    await _send_message(alice, chat)

    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert push_delivery.sent == []


@pytest.mark.asyncio
async def test_sender_does_not_receive_push_for_their_own_event(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    _, alice, bob, chat = await _build_chat(dm=True)
    # Both participants have push subscriptions — only Bob should get pushed.
    await create_push_subscription(user_id=alice.id)
    await create_push_subscription(user_id=bob.id)

    background_jobs.reset()
    await _send_message(alice, chat)

    assert len(push_delivery.sent) == 1
    bob_ledger = await Notification.filter(channel=DeliveryChannel.PUSH, user_id=bob.id).first()
    assert bob_ledger is not None
    alice_ledger = await Notification.filter(channel=DeliveryChannel.PUSH, user_id=alice.id).first()
    assert alice_ledger is None


async def _record_document_comment(document, commenter, content: str = "What do you think?"):
    comment = DocumentComment(
        content=content,
        quoted_text="some quoted text",
        comment_mark_id="mark-1",
        document_id=document.id,
        user_id=commenter.id,
    )
    notifier = Notifier(document, commenter)
    async with notifier.record_and_notify(recordable=comment, action=EventAction.DOCUMENT_COMMENTED) as recording:
        recording.event.details.update({"comment_id": str(comment.id)})
        await comment.save(recording.using_db)


@pytest.mark.asyncio
async def test_document_event_never_pushes_regardless_of_subscription(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """Documents are async — their events never push, whatever the recipient's
    opt-in. Even the strongest signals (explicit per-resource ALL *and* global
    Documents=ALL) stay inbox-only. The creator still gets the inbox/email row."""
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id, time_zone="UTC")
    commenter = await create_user(organization_id=organization.id, time_zone="UTC")
    await create_push_subscription(user_id=creator.id)

    document = await create_document(creator_id=creator.id, organization_id=organization.id)
    await create_collaborator(workspace_id=document.workspace_id, user_id=commenter.id)
    await document.workspace.subscribe(creator.id)
    await SubscriptionPreference.update_for(creator.id, {Document.record_type: SubscriptionLevel.ALL})
    await document.fetch_related("workspace__collaborators__user")

    background_jobs.reset()
    async with JobsOutbox():
        await _record_document_comment(document, commenter)

    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert push_delivery.sent == []
    inbox_ledger = await Notification.filter(channel=DeliveryChannel.EMAIL, user_id=creator.id).first()
    assert inbox_ledger is not None


@pytest.mark.asyncio
async def test_working_hours_gate_drops_event_outside_window(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    _, alice, bob, chat = await _build_chat(dm=True)
    bob.push_working_hours_start = time(9, 0)
    bob.push_working_hours_end = time(9, 1)  # Window so narrow it's almost impossible to hit "now"
    await bob.save()
    await create_push_subscription(user_id=bob.id)

    background_jobs.reset()
    await _send_message(alice, chat)

    # The job was enqueued but dropped silently inside perform() because of the gate.
    assert background_jobs.has_completed_job(SendEventPushJob)
    assert push_delivery.sent == []
    # No ledger row written — the gate fires before push_record_for.
    ledger = await Notification.filter(channel=DeliveryChannel.PUSH, user_id=bob.id).first()
    assert ledger is None


@pytest.mark.asyncio
async def test_mentioned_user_is_excluded_from_event_push_path(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """A mentioned user's push comes from the mention path; the event path skips
    them so the two don't double-fire (and the "mentioned you" copy wins)."""
    _, alice, bob, chat = await _build_chat(num_extra=1)
    await chat.workspace.subscribe(bob.id)
    await create_push_subscription(user_id=bob.id)

    background_jobs.reset()
    async with JobsOutbox():
        message = await ChatMessage.create(chat_id=chat.id, user_id=alice.id, content=f"@[{bob.name}] heads up")
        notifier = Notifier(chat, alice)
        async with notifier.record_and_notify(EventAction.CHAT_MESSAGE_CREATED, recordable=message) as recording:
            await recording.resolve_mentions(message.content)

    # Exactly one push ledger for Bob — the mention path's. No event-path double-push.
    event_ledgers = await Notification.filter(
        channel=DeliveryChannel.PUSH, user_id=bob.id, device_id__isnull=False
    ).count()
    assert event_ledgers == 1


@pytest.mark.asyncio
async def test_post_reply_pushes_creator_and_assignee_only(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """A reply on a post pushes its creator and assignee. A post subscriber who is
    neither — a global Posts=ALL collaborator and an explicit-ALL collaborator —
    is not pushed for a post."""
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id, time_zone="UTC")
    assignee = await create_user(organization_id=organization.id, time_zone="UTC")
    commenter = await create_user(organization_id=organization.id)
    global_all_subscriber = await create_user(organization_id=organization.id)
    explicit_all_subscriber = await create_user(organization_id=organization.id)
    for user in (creator, assignee, global_all_subscriber, explicit_all_subscriber):
        await create_push_subscription(user_id=user.id)
    await SubscriptionPreference.update_for(global_all_subscriber.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await create_post(creator_id=creator.id, organization_id=organization.id)
    await create_collaborator(workspace_id=post.workspace_id, user_id=assignee.id)
    post.workspace.assignee_id = assignee.id
    await post.workspace.save()
    await create_collaborator(workspace_id=post.workspace_id, user_id=explicit_all_subscriber.id)
    await post.workspace.subscribe(explicit_all_subscriber.id)  # explicit ALL, but not creator/assignee
    await post.fetch_related("workspace__collaborators__user")

    background_jobs.reset()
    async with JobsOutbox():
        notifier = Notifier(post, commenter)
        async with notifier.record_and_notify(EventAction.POST_COMMENTED):
            pass

    pushed_user_ids = {
        n.user_id for n in await Notification.filter(channel=DeliveryChannel.PUSH, device_id__isnull=False)
    }
    assert pushed_user_ids == {creator.id, assignee.id}
    assert len(push_delivery.sent) == 2


@pytest.mark.asyncio
async def test_plain_post_created_never_pushes(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """Publishing a post (POST_CREATED) pushes no one — even a global Posts=ALL
    subscriber. They still get the inbox entry via the subscription cascade."""
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    recipient = await create_user(organization_id=organization.id)
    await create_push_subscription(user_id=recipient.id)
    await SubscriptionPreference.update_for(recipient.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await create_post(creator_id=creator.id, organization_id=organization.id)
    await post.fetch_related("workspace")

    background_jobs.reset()
    async with JobsOutbox():
        notifier = Notifier(post, creator)
        async with notifier.record_and_notify(EventAction.POST_CREATED):
            pass

    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert push_delivery.sent == []


@pytest.mark.asyncio
async def test_announcement_broadcast_reaches_inbox_without_pushing(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """An announcement reaches the whole org's inbox but never pushes — posts
    don't move at chat pace, so an org-wide blast shouldn't buzz every device."""
    organization = await create_organization()
    author = await create_user(organization_id=organization.id)
    member = await create_user(organization_id=organization.id, time_zone="UTC", last_logged_in_at=datetime.now(UTC))
    await create_push_subscription(user_id=member.id)

    post = await create_post(creator_id=author.id, organization_id=organization.id, is_announcement=True)
    await post.fetch_related("workspace__collaborators__user")

    background_jobs.reset()
    async with JobsOutbox():
        notifier = Notifier(post, author)
        async with notifier.record_and_notify(EventAction.POST_ANNOUNCED):
            pass

    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert push_delivery.sent == []
    # Inbox reach is unaffected — the announcement still lands in the member's mailbox.
    member_entry = await MailboxEntry.get_or_none(owner_id=member.id, resource_gid=str(post.global_id))
    assert member_entry is not None


@pytest.mark.asyncio
async def test_announcement_mention_still_pushes(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """The announcement broadcast doesn't push, but an @mention inside it still
    names you specifically — so it pushes via the mention path (SendMentionPushJob)."""
    organization = await create_organization()
    author = await create_user(name="Alice Clams", organization_id=organization.id)
    mentioned = await create_user(
        name="Bob Clams", organization_id=organization.id, time_zone="UTC", last_logged_in_at=datetime.now(UTC)
    )
    await create_push_subscription(user_id=mentioned.id)

    post = await create_post(
        title="Big news", creator_id=author.id, organization_id=organization.id, is_announcement=True
    )
    await create_collaborator(workspace_id=post.workspace_id, user_id=mentioned.id)
    await post.fetch_related("workspace__collaborators__user")

    background_jobs.reset()
    async with JobsOutbox():
        notifier = Notifier(post, author)
        async with notifier.record_and_notify(EventAction.POST_ANNOUNCED) as recording:
            await recording.resolve_mentions(f"Heads up @[{mentioned.name}]", recordable=post)

    # The mention pushes; the broadcast itself doesn't, so it's exactly one send.
    assert background_jobs.has_completed_job(SendMentionPushJob)
    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert len(push_delivery.sent) == 1


@pytest.mark.asyncio
async def test_assignment_pushes_the_assignee_only_with_assignment_copy(
    push_enabled, background_jobs: InlineJobs, push_delivery: FakePushDelivery
):
    """Assignment pushes the assignee like an @mention — regardless of subscription level, and
    with 'assigned this to you' copy. Only the assignee is pushed (not the post creator), and
    the actor who did the assigning is excluded."""
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id, time_zone="UTC")
    manager = await create_user(name="Manny Manager", organization_id=organization.id, time_zone="UTC")
    assignee = await create_user(organization_id=organization.id, time_zone="UTC")
    for user in (creator, manager, assignee):
        await create_push_subscription(user_id=user.id)
    # Level below ALL must not silence being assigned.
    await SubscriptionPreference.update_for(assignee.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})

    post = await create_post(creator_id=creator.id, organization_id=organization.id, title="Ship it")
    await create_collaborator(workspace_id=post.workspace_id, user_id=manager.id)
    await post.fetch_related("workspace")

    background_jobs.reset()
    async with JobsOutbox():
        notifier = Notifier(post, manager)
        async with notifier.record_and_notify(action=EventAction.ASSIGNED, creator_id=manager.id) as recording:
            await post.collaboration.assign_to(assignee, manager, using_db=recording.using_db)
            recording.event.details = {"assignee": assignee.field_values}

    pushed_user_ids = {
        n.user_id for n in await Notification.filter(channel=DeliveryChannel.PUSH, device_id__isnull=False)
    }
    assert pushed_user_ids == {assignee.id}
    assert len(push_delivery.sent) == 1
    assert push_delivery.sent[0].payload["body"] == "Manny Manager assigned this to you"
