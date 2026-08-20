import pytest
from fastapi import status

from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import SubscriptionPreference
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post
from config.enums import Sharing, SubscriptionLevel
from infra.email import FakeDelivery
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import create_group, create_group_member, create_post_group_mute, create_user


@pytest.mark.asyncio
async def test_default_subscriptions(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    # Test subscription — subscriber gets a mailbox entry
    await SubscriptionPreference.update_for(other_user.id, {Post.record_type: SubscriptionLevel.ALL})
    response = await client.post("/api/posts", json={"title": "Lunch", "content": "What should we eat for lunch?"})
    assert response.status_code == status.HTTP_201_CREATED

    post = await Post.filter(title="Lunch").first()
    assert post is not None
    entry = await MailboxEntry.filter(owner_id=other_user.id, resource_gid=str(post.global_id)).first()
    assert entry is not None
    assert entry.is_inbox

    # Test ignoring — no mailbox entry created
    await SubscriptionPreference.update_for(other_user.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})
    response = await client.post("/api/posts", json={"title": "Dinner", "content": "What should we eat for dinner?"})
    assert response.status_code == status.HTTP_201_CREATED

    dinner_post = await Post.filter(title="Dinner").first()
    assert dinner_post is not None
    entry = await MailboxEntry.filter(owner_id=other_user.id, resource_gid=str(dinner_post.global_id)).first()
    assert entry is None


@pytest.mark.asyncio
async def test_private_subscriptions(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    await SubscriptionPreference.update_for(other_user.id, {Post.record_type: SubscriptionLevel.ALL})

    response = await client.post("/api/posts", json={"title": "Lunch", "content": "What should we eat for lunch?"})
    assert response.status_code == status.HTTP_201_CREATED
    post = await Post.first().prefetch_related("workspace__collaborators__user")
    assert post is not None

    # Test organization sharing — subscriber gets a mailbox entry on comment
    post.sharing = Sharing.ORGANIZATION
    await post.save()

    response = await client.post(f"/api/posts/{post.id}/comments", json={"content": "Maybe tacos"})
    assert response.status_code == status.HTTP_201_CREATED
    entry = await MailboxEntry.filter(owner_id=other_user.id, resource_gid=str(post.global_id)).first()
    assert entry is not None
    assert entry.is_inbox

    # Test ignoring private workspace — no mailbox entry update
    await entry.delete()
    post.sharing = Sharing.PRIVATE
    await post.save()

    response = await client.post(f"/api/posts/{post.id}/comments", json={"content": "Maybe pizza"})
    assert response.status_code == status.HTTP_201_CREATED
    entry = await MailboxEntry.filter(owner_id=other_user.id, resource_gid=str(post.global_id)).first()
    assert entry is None


@pytest.mark.asyncio
async def test_mention_notifications(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Clams", organization_id=creator.organization_id)
    bob = await create_user(name="Bob Clams", organization_id=creator.organization_id)
    await SubscriptionPreference.filter(subscriber_id=bob.id).delete()

    response = await client.post("/api/posts", json={"title": "Lunch", "content": "Hey @[Alice Clams]"})
    assert response.status_code == status.HTTP_201_CREATED
    post = await Post.first().prefetch_related("workspace__mentions")
    assert post is not None
    assert await post.workspace.mentions.all().count() == 1
    latest_mention = await post.workspace.mentions.order_by("-created_at").first()
    assert latest_mention is not None
    assert latest_mention.mentioned_id == alice.id
    assert latest_mention.creator_id == creator.id
    assert latest_mention.event_id is not None

    # Mentioned user gets a mailbox entry
    alice_entry = await MailboxEntry.filter(owner_id=alice.id, resource_gid=str(post.global_id)).first()
    assert alice_entry is not None
    assert alice_entry.is_inbox

    # Test normal mentions via comment
    response = await client.post(f"/api/posts/{post.id}/comments", json={"content": "Hey @[Alice Clams]?"})
    assert response.status_code == status.HTTP_201_CREATED

    # Creator should not have a self-notification entry in inbox
    creator_entry = await MailboxEntry.filter(owner_id=creator.id, resource_gid=str(post.global_id)).first()
    assert creator_entry is None or not creator_entry.is_inbox
    # Bob should have no entry (not mentioned, not subscribed)
    bob_entry = await MailboxEntry.filter(owner_id=bob.id, resource_gid=str(post.global_id)).first()
    assert bob_entry is None

    assert await post.workspace.mentions.all().count() == 2
    latest_mention = await post.workspace.mentions.order_by("-created_at").first()
    assert latest_mention is not None
    assert latest_mention.mentioned_id == alice.id
    assert latest_mention.creator_id == creator.id
    assert latest_mention.event_id is not None

    # Test being brought into the workspace via mention
    response = await client.post(f"/api/posts/{post.id}/comments", json={"content": "Hey there @[Bob Clams]?"})
    assert response.status_code == status.HTTP_201_CREATED

    # Bob gets a mailbox entry from mention
    bob_entry = await MailboxEntry.filter(owner_id=bob.id, resource_gid=str(post.global_id)).first()
    assert bob_entry is not None
    assert bob_entry.is_inbox

    assert await post.workspace.mentions.all().count() == 3
    latest_mention = await post.workspace.mentions.order_by("-created_at").first()
    assert latest_mention is not None
    assert latest_mention.mentioned_id == bob.id
    assert latest_mention.creator_id == creator.id
    assert latest_mention.event_id is not None
    # Mentions are one-shot: they deliver to the mentioned user but do not
    # write subscription rows.
    assert await post.workspace.subscriptions.filter(subscriber_id=bob.id).count() == 0

    # Test updating content with new and existing mentions
    latest_comment = await post.comments.order_by("-created_at").first()
    assert latest_comment is not None
    response = await client.patch(
        f"/api/posts/{post.id}/comments/{latest_comment.id}",
        json={"content": "Hey @[Alice Clams] and @[Bob Clams]"},
    )
    assert response.status_code == status.HTTP_200_OK

    assert await post.workspace.mentions.all().count() == 4
    latest_mention = await post.workspace.mentions.order_by("-created_at").first()
    assert latest_mention is not None
    assert latest_mention.mentioned_id == alice.id
    assert latest_mention.creator_id == creator.id
    assert latest_mention.event_id is None
    assert await post.workspace.subscriptions.filter(subscriber_id=alice.id).count() == 0


@pytest.mark.asyncio
async def test_self_mention_notifies_author(client: AppClient, background_jobs: InlineJobs):
    # Mentioning yourself behaves like a teammate mentioning you: a Mention row is created
    # and your inbox row is marked unread, despite you being the event's sender.
    creator = await client.get_default_user()

    response = await client.post(
        "/api/posts", json={"title": "Reminder", "content": f"Note to self @[{creator.display_name}]"}
    )
    assert response.status_code == status.HTTP_201_CREATED
    post = await Post.first().prefetch_related("workspace__mentions")
    assert post is not None

    self_mention = await post.workspace.mentions.order_by("-created_at").first()
    assert self_mention is not None
    assert self_mention.mentioned_id == creator.id
    assert self_mention.creator_id == creator.id
    assert self_mention.event_id is not None

    # The author's own inbox row is unread — the self-mention reached them even though they sent it.
    creator_entry = await MailboxEntry.filter(owner_id=creator.id, resource_gid=str(post.global_id)).first()
    assert creator_entry is not None
    assert creator_entry.is_inbox


@pytest.mark.asyncio
async def test_meeting_subscriptions(client: AppClient, email_delivery: FakeDelivery):
    user = await create_user(name="William Penn")
    other_user = await create_user(organization_id=user.organization_id, name="Benjamin Franklin")

    test_transcript = """
    William Penn: Don't break my bell
    Benjamin Franklin: It'll look better broken
    """

    await SubscriptionPreference.update_for(user.id, {Meeting.record_type: SubscriptionLevel.ALL})
    await SubscriptionPreference.update_for(other_user.id, {Meeting.record_type: SubscriptionLevel.ALL})

    with client.current_user_as(user):
        response = await client.post(
            "/api/meetings",
            json={"type": "transcript", "title": "Bell Transportation", "transcript": test_transcript},
        )
        assert response.status_code == status.HTTP_201_CREATED

    assert len(email_delivery.messages) == 2
    messages_sent_to = [message.to for message in email_delivery.messages]
    assert user.email in messages_sent_to
    assert other_user.email in messages_sent_to

    # Flip back to the default RELEVANT_ONLY. The creator is still implicitly resolved
    # to ALL by the subscriber resolver, so they get the "your meeting is processed"
    # email even with a global RELEVANT_ONLY preference — async processing means they
    # may not be on the page when it completes. other_user is neither creator nor
    # @-mentioned, so they receive nothing.
    email_delivery.reset()
    await SubscriptionPreference.update_for(user.id, {Meeting.record_type: SubscriptionLevel.RELEVANT_ONLY})
    await SubscriptionPreference.update_for(other_user.id, {Meeting.record_type: SubscriptionLevel.RELEVANT_ONLY})

    with client.current_user_as(user):
        response = await client.post(
            "/api/meetings",
            json={"type": "transcript", "title": "Bell Transportation", "transcript": test_transcript},
        )
        assert response.status_code == status.HTTP_201_CREATED

    assert len(email_delivery.messages) == 1
    assert email_delivery.messages[0].to == user.email


@pytest.mark.asyncio
async def test_group_mute_skips_notification(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    subscriber = await create_user(organization_id=creator.organization_id)
    group = await create_group(organization_id=creator.organization_id)
    await create_group_member(group_id=group.id, user_id=creator.id)
    await create_group_member(group_id=group.id, user_id=subscriber.id)

    # Subscriber has the default global preference (relevant_only) — group
    # membership alone should deliver the first post.
    response = await client.post(
        "/api/posts", json={"title": "Group Post", "content": "Hello group", "group_id": str(group.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED
    post = await Post.filter(title="Group Post").first()
    assert post is not None
    entry = await MailboxEntry.filter(owner_id=subscriber.id, resource_gid=str(post.global_id)).first()
    assert entry is not None

    # Subscriber mutes the group, then a comment on the same post lands —
    # subscriber should NOT get a mailbox entry for the comment.
    await entry.delete()
    await create_post_group_mute(user_id=subscriber.id, group_id=group.id)

    response = await client.post(f"/api/posts/{post.id}/comments", json={"content": "Follow up"})
    assert response.status_code == status.HTTP_201_CREATED
    entry = await MailboxEntry.filter(owner_id=subscriber.id, resource_gid=str(post.global_id)).first()
    assert entry is None
