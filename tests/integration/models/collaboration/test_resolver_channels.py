import pytest

from app.models.collaboration.mailbox import InboxUpdate
from app.models.collaboration.workspace import (
    NotificationPolicy,
    SubscriberResolver,
    Subscription,
    SubscriptionPreference,
)
from app.models.workspaces.goals import Goal
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post
from config.enums import EventAction, SubscriptionLevel
from tests.helpers.factories import (
    create_chat,
    create_collaborator,
    create_event,
    create_goal,
    create_meeting,
    create_post,
    create_user,
)


@pytest.mark.asyncio
async def test_resolve_for_push_force_includes_dm_collaborators():
    # DM chats force-include all collaborators via
    # ChatNotificationPolicy.force_include_all_collaborators_for_push. A
    # collaborator at the default level (no explicit Subscription) still gets
    # push because DM-as-resource opts everyone in. The chat factory creates
    # exactly the two collaborators added below, so chat.type resolves to DM.
    sender = await create_user()
    recipient = await create_user(organization_id=sender.organization_id)
    chat = await create_chat(organization_id=sender.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=sender.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)
    await chat.fetch_related("workspace__collaborators__user")
    assert chat.type.is_dm

    event = await create_event(chat.workspace, creator_id=sender.id, action=EventAction.CHAT_MESSAGE_CREATED)

    resolver = SubscriberResolver(workspace=chat.workspace)
    push_recipients = await resolver.resolve_for_push(event, mention_user_ids=set(), exclude_user_id=sender.id)
    assert {u.id for u in push_recipients} == {recipient.id}


@pytest.mark.asyncio
async def test_resolve_for_push_excludes_mentioned_users():
    # Mentioned users get a SendMentionPushJob via Notifier.notify_mentions, so
    # dropping them from resolve_for_push avoids a double-fire (and stops the
    # event push from winning the ledger race, which would mask the "mentioned
    # you" copy). A post reply pushes both owners; mention one and only the other
    # remains in the event-push set.
    creator = await create_user()
    assignee = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, user_id=assignee.id)
    post.workspace.assignee_id = assignee.id
    await post.workspace.save()

    commenter = await create_user(organization_id=creator.organization_id)
    event = await create_event(post.workspace, creator_id=commenter.id, action=EventAction.POST_COMMENTED)

    resolver = SubscriberResolver(workspace=post.workspace)
    push_recipients = await resolver.resolve_for_push(
        event,
        mention_user_ids={creator.id},
        exclude_user_id=commenter.id,
    )
    assert {u.id for u in push_recipients} == {assignee.id}


@pytest.mark.asyncio
async def test_resolve_for_email_empty_for_skip_resources():
    # Chats and Posts are email_delivery.SKIP — resolve_for_email returns an
    # empty list regardless of who would otherwise be a candidate.
    sender = await create_user()
    bystander = await create_user(organization_id=sender.organization_id)
    await SubscriptionPreference.update_for(bystander.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await create_post(creator_id=sender.id, organization_id=sender.organization_id)
    await post.fetch_related("workspace")
    event = await create_event(post.workspace, creator_id=sender.id, action=EventAction.POST_COMMENTED)

    resolver = SubscriberResolver(workspace=post.workspace)
    assert await resolver.resolve_for_email(event, mention_user_ids=set(), exclude_user_id=sender.id) == []


@pytest.mark.asyncio
async def test_resolve_for_email_returns_subscribers_for_send_resources():
    # Meetings are email_delivery.SEND: resolve_for_email returns ALL-level
    # collaborators (sender excluded), unlike the SKIP resources above.
    creator = await create_user()
    subscriber = await create_user(organization_id=creator.organization_id)
    meeting = await create_meeting(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=meeting.workspace_id, user_id=subscriber.id)
    await SubscriptionPreference.update_for(subscriber.id, {Meeting.record_type: SubscriptionLevel.ALL})
    await meeting.fetch_related("workspace__collaborators__user")

    event = await create_event(meeting.workspace, creator_id=creator.id, action=EventAction.MEETING_AGENDA_UPDATED)

    resolver = SubscriberResolver(workspace=meeting.workspace)
    email_recipients = await resolver.resolve_for_email(event, mention_user_ids=set(), exclude_user_id=creator.id)
    assert subscriber.id in {u.id for u in email_recipients}
    assert creator.id not in {u.id for u in email_recipients}


@pytest.mark.asyncio
async def test_resolve_for_inbox_includes_direct_recipients_below_all():
    # resolve_for_inbox opts a mention recipient in even at RELEVANT_ONLY — the
    # settings page promises "@mentions always reach you". Chat defaults to ALL,
    # so we downgrade `mentioned` via a Subscription row to actually exercise the
    # mention branch rather than plain membership.
    sender = await create_user()
    mentioned = await create_user(organization_id=sender.organization_id)
    chat = await create_chat(organization_id=sender.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=sender.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=mentioned.id)
    third = await create_user(organization_id=sender.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=third.id)
    await Subscription.create(
        workspace_id=chat.workspace_id, subscriber_id=mentioned.id, level=SubscriptionLevel.RELEVANT_ONLY
    )
    await chat.fetch_related("workspace__collaborators__user")

    event = await create_event(chat.workspace, creator_id=sender.id, action=EventAction.CHAT_MESSAGE_CREATED)

    reached_without_mention = await SubscriberResolver(workspace=chat.workspace).resolve_for_inbox(
        event, direct_recipients=[]
    )
    assert mentioned.id not in {u.id for u in reached_without_mention}

    reached_with_mention = await SubscriberResolver(workspace=chat.workspace).resolve_for_inbox(
        event, direct_recipients=[mentioned]
    )
    assert mentioned.id in {u.id for u in reached_with_mention}


@pytest.mark.asyncio
async def test_resolve_for_inbox_includes_sender():
    # resolve_for_inbox is reach-only and includes the sender — whether the sender's
    # row alerts or merely refreshes is InboxUpdate.for_event's decision, not the resolver's.
    sender = await create_user()
    other = await create_user(organization_id=sender.organization_id)
    chat = await create_chat(organization_id=sender.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=sender.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)
    await chat.fetch_related("workspace__collaborators__user")

    event = await create_event(chat.workspace, creator_id=sender.id, action=EventAction.CHAT_MESSAGE_CREATED)
    reached = await SubscriberResolver(workspace=chat.workspace).resolve_for_inbox(event, direct_recipients=[])
    assert sender.id in {u.id for u in reached}


def test_inbox_update_for_event_cascade():
    # The whole inbox rule in one place: a reached event marks your row unread, unless
    # you sent it (then it's just refreshed); otherwise any row you already have is
    # refreshed; otherwise nothing. Reach dominates row state.
    def for_normal(**kwargs) -> InboxUpdate:
        return InboxUpdate.for_event(action=EventAction.CHAT_MESSAGE_CREATED, user_is_direct_recipient=False, **kwargs)

    assert (
        for_normal(event_reaches_user=True, user_is_sender=False, user_has_existing_row=False)
        is InboxUpdate.MARK_UNREAD
    )
    assert (
        for_normal(event_reaches_user=True, user_is_sender=True, user_has_existing_row=False)
        is InboxUpdate.REFRESH_CONTENT
    )
    assert (
        for_normal(event_reaches_user=False, user_is_sender=False, user_has_existing_row=True)
        is InboxUpdate.REFRESH_CONTENT
    )
    assert (
        for_normal(event_reaches_user=False, user_is_sender=False, user_has_existing_row=False) is InboxUpdate.IGNORE
    )
    assert (
        for_normal(event_reaches_user=True, user_is_sender=False, user_has_existing_row=True)
        is InboxUpdate.MARK_UNREAD
    )
    # Mentioning yourself surfaces your own row past the content gate (which can't see your
    # own activity), exactly like a teammate mentioning you — the sender carve-out is overridden.
    assert (
        InboxUpdate.for_event(
            action=EventAction.CHAT_MESSAGE_CREATED,
            event_reaches_user=True,
            user_is_sender=True,
            user_has_existing_row=False,
            user_is_direct_recipient=True,
        )
        is InboxUpdate.MARK_UNREAD_FORCED
    )
    # A direct ask (@mention or assignment) to a non-sender surfaces past the resource content
    # gate — this is what lets a mention/assignment reach the inbox on a Gmail-archived email
    # thread, where the plain MARK_UNREAD path would be swallowed by the archive gate.
    assert (
        InboxUpdate.for_event(
            action=EventAction.CHAT_MESSAGE_CREATED,
            event_reaches_user=True,
            user_is_sender=False,
            user_has_existing_row=False,
            user_is_direct_recipient=True,
        )
        is InboxUpdate.MARK_UNREAD_FORCED
    )


def test_inbox_update_for_decided_forces_unread_past_the_content_gate():
    # A DECIDED mark reaches every non-sender and must surface even though it creates no
    # message the content gate can see — so it returns the FORCED variant, not plain MARK_UNREAD.
    def for_decided(**kwargs) -> InboxUpdate:
        return InboxUpdate.for_event(action=EventAction.DECIDED, user_is_direct_recipient=False, **kwargs)

    assert (
        for_decided(event_reaches_user=True, user_is_sender=False, user_has_existing_row=False)
        is InboxUpdate.MARK_UNREAD_FORCED
    )
    assert (
        for_decided(event_reaches_user=True, user_is_sender=True, user_has_existing_row=False)
        is InboxUpdate.REFRESH_CONTENT
    )


def test_inbox_update_for_content_revision_action_only_alerts_new_mentions():
    # An edit/delete must not re-alert caught-up readers: a reached collaborator (or one with
    # an existing row) gets a content refresh, only a newly-@mentioned user is marked unread —
    # and that surfaces past the content gate (FORCED), since the edit isn't new content itself.
    def for_edit(**kwargs) -> InboxUpdate:
        return InboxUpdate.for_event(action=EventAction.EMAIL_THREAD_COMMENT_EDITED, **kwargs)

    # A reached collaborator who already had a row — a re-mention or plain edit — only refreshes.
    assert (
        for_edit(
            event_reaches_user=True, user_is_sender=False, user_has_existing_row=True, user_is_direct_recipient=True
        )
        is InboxUpdate.REFRESH_CONTENT
    )
    # A genuinely new mention (no prior row) surfaces past the content gate.
    assert (
        for_edit(
            event_reaches_user=True, user_is_sender=False, user_has_existing_row=False, user_is_direct_recipient=True
        )
        is InboxUpdate.MARK_UNREAD_FORCED
    )
    assert (
        for_edit(
            event_reaches_user=False, user_is_sender=False, user_has_existing_row=False, user_is_direct_recipient=False
        )
        is InboxUpdate.IGNORE
    )
    # A self-@mention on your own edit never self-alerts — it refreshes, not MARK_UNREAD.
    # (Fresh events do self-alert; see test_inbox_update_for_event_cascade.)
    assert (
        for_edit(
            event_reaches_user=True, user_is_sender=True, user_has_existing_row=False, user_is_direct_recipient=True
        )
        is InboxUpdate.REFRESH_CONTENT
    )


@pytest.mark.asyncio
async def test_resolve_for_inbox_reads_force_include_through_the_policy(monkeypatch):
    # The resolver reads force-include via `resource.notification_policy`, never by
    # branching on the resource type. Goals carry the base policy
    # (force_include_for_inbox = False), so a below-ALL
    # collaborator isn't reached. Swap in a policy that lies — returns True where
    # the base returns False — and the resolver must pick it up, force-including
    # that collaborator. A resolver that hardcoded `isinstance(resource, Chat)`
    # would ignore the policy and fail here.
    creator = await create_user()
    other = await create_user(organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=goal.workspace_id, user_id=other.id)
    await goal.fetch_related("workspace__collaborators__user")

    event = await create_event(goal.workspace, creator_id=creator.id, action=EventAction.GOAL_COMMENTED)

    reached_baseline = await SubscriberResolver(workspace=goal.workspace).resolve_for_inbox(
        event, direct_recipients=[]
    )
    assert other.id not in {u.id for u in reached_baseline}

    class _ForceIncludePolicy(NotificationPolicy):
        def force_include_for_inbox(self, action=None) -> bool:
            return True

    monkeypatch.setattr(Goal, "notification_policy", property(lambda self: _ForceIncludePolicy(self.workspace)))

    reached_with_policy = await SubscriberResolver(workspace=goal.workspace).resolve_for_inbox(
        event, direct_recipients=[]
    )
    assert other.id in {u.id for u in reached_with_policy}


@pytest.mark.asyncio
async def test_resolve_for_email_drops_mentioned_users():
    # Same no-double-fire rule as push: a mentioned user gets a SendMentionJob,
    # not a SendEventEmailJob.
    creator = await create_user()
    other = await create_user(organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=goal.workspace_id, user_id=other.id)
    await goal.fetch_related("workspace__collaborators__user")

    event = await create_event(goal.workspace, creator_id=other.id, action=EventAction.GOAL_COMMENTED)

    resolver = SubscriberResolver(workspace=goal.workspace)
    email_recipients = await resolver.resolve_for_email(
        event,
        mention_user_ids={creator.id},
        exclude_user_id=other.id,
    )
    assert creator.id not in {u.id for u in email_recipients}
