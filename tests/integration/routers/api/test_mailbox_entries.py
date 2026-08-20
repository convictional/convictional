from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import status

from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.collaboration.workspace import SubscriptionPreference
from app.models.workspaces.chat import Chat
from app.models.workspaces.email.client import FakeEmailClient
from app.models.workspaces.email.mailbox import EmailMailboxEntry
from app.models.workspaces.email.thread import EmailThread
from app.models.workspaces.goals import Goal, GoalComment, GoalMailboxEntry
from app.models.workspaces.posts import Post, PostComment, PostMailboxEntry
from config.enums import EmailLabel, EmailMessageType, EventAction, GoalStatus, SubscriptionLevel
from config.settings import settings
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_collaborator,
    create_email_message,
    create_email_thread_comment,
    create_goal,
    create_mailbox_entry,
    create_post,
    create_user,
)


async def _chat_with_entry(client: AppClient) -> tuple[MailboxEntry, Chat]:
    user = await client.get_default_user()
    other = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)
    await create_chat_message(chat_id=chat.id, user_id=other.id, content="Hello")
    await chat.refresh_from_db()
    await Mailbox.sync(chat)

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user.id)
    return entry, chat


async def _email_thread_with_entry(
    client: AppClient,
    *,
    external_thread_id: str | None = "ext-thread-1",
    creator_id=None,
) -> tuple[MailboxEntry, EmailThread]:
    user = await client.get_default_user()
    creator_id = creator_id or user.id
    factory_kwargs: dict = {
        "organization_id": user.organization_id,
        "creator_id": creator_id,
    }
    if external_thread_id is not None:
        factory_kwargs["external_thread_id"] = external_thread_id
    message = await create_email_message(**factory_kwargs)
    thread = await EmailThread.get(id=message.thread_id)
    if external_thread_id is None:
        thread.external_thread_id = None
        await thread.save(update_fields=["external_thread_id"])
    entry = await create_mailbox_entry(
        owner_id=user.id,
        organization_id=user.organization_id,
        resource_gid=thread.global_id,
    )
    return entry, thread


async def _goal_with_entry(client: AppClient) -> tuple[MailboxEntry, Goal]:
    user = await client.get_default_user()
    owner = await create_user(organization_id=user.organization_id)
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=owner.id,
        owner_id=owner.id,
        title="Ship Q3",
        description="Improve onboarding conversion",
        progress=0.5,
    )
    await goal.fetch_related("workspace")
    await create_collaborator(workspace_id=goal.workspace_id, user_id=user.id)
    await SubscriptionPreference.update_for(user.id, {Goal.record_type: SubscriptionLevel.ALL})

    comment = GoalComment(goal_id=goal.id, user_id=owner.id, content="Kicking this off")
    async with goal.workspace.record(EventAction.GOAL_COMMENTED, recordable=comment, creator_id=owner.id) as rec:
        await comment.save(rec.using_db)
    await GoalMailboxEntry(goal).sync(event=rec.event, direct_recipients=[])

    entry = await MailboxEntry.get(resource_gid=str(goal.global_id), owner_id=user.id)
    return entry, goal


async def _post_with_entry(client: AppClient) -> tuple[MailboxEntry, Post]:
    user = await client.get_default_user()
    other = await create_user(organization_id=user.organization_id)
    post = await create_post(creator_id=other.id, organization_id=user.organization_id, title="Shared")
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, user_id=user.id)
    await post.workspace.subscribe(user.id)
    await PostMailboxEntry(post).sync()

    entry = await MailboxEntry.get(resource_gid=str(post.global_id), owner_id=user.id)
    return entry, post


@pytest.mark.asyncio
async def test_mark_read_and_unread_for_chat(client: AppClient):
    entry, _ = await _chat_with_entry(client)
    assert entry.is_unread

    response = await client.post(f"/api/mailbox_entries/{entry.id}/mark_read")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await entry.refresh_from_db()
    assert entry.is_read

    response = await client.post(f"/api/mailbox_entries/{entry.id}/mark_unread")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await entry.refresh_from_db()
    assert entry.is_unread


@pytest.mark.asyncio
async def test_archive_and_unarchive_for_chat(client: AppClient):
    entry, _ = await _chat_with_entry(client)

    response = await client.post(f"/api/mailbox_entries/{entry.id}/archive")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await entry.refresh_from_db()
    assert entry.is_archived

    response = await client.post(f"/api/mailbox_entries/{entry.id}/unarchive")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await entry.refresh_from_db()
    assert not entry.is_archived


@pytest.mark.asyncio
async def test_snooze_and_unsnooze_for_chat(client: AppClient):
    entry, _ = await _chat_with_entry(client)
    snoozed_until = (datetime.now(UTC) + timedelta(hours=1)).replace(microsecond=0)

    response = await client.post(
        f"/api/mailbox_entries/{entry.id}/snooze",
        json={"snoozed_until": snoozed_until.isoformat()},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await entry.refresh_from_db()
    assert entry.is_snoozed
    assert entry.snoozed_until == snoozed_until

    # The snooze confirmation ("Snoozed until …") is rendered client-side by the React
    # island's UndoToast, not a server flash, so the endpoint returns no message.
    flashes = (await client.get("/api/users/me")).json()["flashes"]
    assert flashes == []

    response = await client.post(f"/api/mailbox_entries/{entry.id}/unsnooze")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await entry.refresh_from_db()
    assert not entry.is_snoozed


@pytest.mark.asyncio
async def test_snooze_to_past_time_is_rejected(client: AppClient):
    # Snoozing to a past time would drop the entry out of every view until the unsnooze
    # scan reaps it, so the endpoint rejects it with a 422 rather than persisting it.
    entry, _ = await _chat_with_entry(client)
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    response = await client.post(
        f"/api/mailbox_entries/{entry.id}/snooze",
        json={"snoozed_until": past},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    await entry.refresh_from_db()
    assert not entry.is_snoozed


@pytest.mark.asyncio
async def test_snooze_to_naive_time_is_rejected(client: AppClient):
    # A naive datetime (no offset) is ambiguous — rather than silently assume UTC, the
    # endpoint rejects it so a client sending local wall-clock time fails loudly.
    entry, _ = await _chat_with_entry(client)
    naive = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None).isoformat()

    response = await client.post(
        f"/api/mailbox_entries/{entry.id}/snooze",
        json={"snoozed_until": naive},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    await entry.refresh_from_db()
    assert not entry.is_snoozed


@pytest.mark.asyncio
async def test_actions_for_post(client: AppClient):
    entry, _ = await _post_with_entry(client)

    response = await client.post(f"/api/mailbox_entries/{entry.id}/archive")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await entry.refresh_from_db()
    assert entry.is_archived

    response = await client.post(f"/api/mailbox_entries/{entry.id}/mark_unread")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await entry.refresh_from_db()
    assert entry.is_unread


@pytest.mark.asyncio
async def test_email_thread_actions_call_email_client(client: AppClient):
    entry, thread = await _email_thread_with_entry(client)

    cases = [
        ("archive", "archive_thread"),
        ("unarchive", "unarchive_thread"),
        ("mark_read", "mark_thread_read"),
        ("mark_unread", "mark_thread_unread"),
        ("unsnooze", "unarchive_thread"),
    ]
    for action, client_method in cases:
        with patch.object(FakeEmailClient, client_method, new_callable=AsyncMock) as spy:
            response = await client.post(f"/api/mailbox_entries/{entry.id}/{action}")
            assert response.status_code == status.HTTP_204_NO_CONTENT, action
            spy.assert_called_once()
            kwargs = spy.call_args.kwargs
            assert kwargs["external_thread_id"] == thread.external_thread_id
            assert kwargs["user_id"] == thread.creator_id

    snoozed_until = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    with patch.object(FakeEmailClient, "archive_thread", new_callable=AsyncMock) as spy:
        response = await client.post(
            f"/api/mailbox_entries/{entry.id}/snooze",
            json={"snoozed_until": snoozed_until},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        spy.assert_called_once()


@pytest.mark.asyncio
async def test_email_thread_skips_email_client_when_not_original_recipient(client: AppClient):
    user = await client.get_default_user()
    other = await create_user(organization_id=user.organization_id)
    entry, _ = await _email_thread_with_entry(
        client,
        creator_id=other.id,
        external_thread_id="ext-thread-shared",
    )

    with patch.object(FakeEmailClient, "archive_thread", new_callable=AsyncMock) as spy:
        response = await client.post(f"/api/mailbox_entries/{entry.id}/archive")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        spy.assert_not_called()


@pytest.mark.asyncio
async def test_email_thread_skips_email_client_when_no_external_thread_id(client: AppClient):
    entry, _ = await _email_thread_with_entry(client, external_thread_id=None)

    with patch.object(FakeEmailClient, "archive_thread", new_callable=AsyncMock) as spy:
        response = await client.post(f"/api/mailbox_entries/{entry.id}/archive")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        spy.assert_not_called()


@pytest.mark.asyncio
async def test_returns_404_for_missing_entry(client: AppClient):
    await client.get_default_user()
    missing_id = uuid4()
    response = await client.post(f"/api/mailbox_entries/{missing_id}/archive")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_returns_404_for_entry_owned_by_another_user(client: AppClient):
    await client.get_default_user()
    stranger = await create_user()
    chat = await create_chat(organization_id=stranger.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=stranger.id)
    await create_chat_message(chat_id=chat.id, user_id=stranger.id, content="Private")
    await Mailbox.sync(chat)

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=stranger.id)

    response = await client.post(f"/api/mailbox_entries/{entry.id}/archive")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_requires_authentication(client: AppClient):
    entry, _ = await _chat_with_entry(client)
    with client.logged_out():
        response = await client.post(f"/api/mailbox_entries/{entry.id}/archive")
    assert response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}


#
# Inbox endpoints
#
#


@pytest.mark.asyncio
async def test_list_inbox_returns_chat_entries(client: AppClient):
    entry, chat = await _chat_with_entry(client)

    response = await client.get("/api/mailbox_entries?view=inbox")
    assert response.status_code == status.HTTP_200_OK
    # no-store (not the default no-cache) so back/forward navigation can't serve a
    # stale snapshot showing a just-read entry as unread — see issue #8343.
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["has_more"] is False
    assert body["next_cursor"] is None
    assert "synced_at" in body

    items = {item["id"]: item for item in body["entries"]}
    assert str(entry.id) in items
    item = items[str(entry.id)]
    assert item["resource_type"] == "Chat"
    assert item["is_unread"] is True
    assert item["is_archived"] is False
    assert item["chat"] is not None
    assert item["chat"]["is_dm"] is True
    # A message is the newest thing, so the preview is the message (not an activity line).
    assert item["chat"]["preview_kind"] == "comment"
    assert item["chat"]["last_comment"] == "Hello"
    assert item["href"].startswith(f"/chats/{chat.id}")


@pytest.mark.asyncio
async def test_list_inbox_serializes_chat_activity_event(client: AppClient):
    # A chat-level event newer than the last message (here a rename) supersedes the message preview:
    # it ships as raw action + Event details for the client to phrase the "activity" line itself.
    entry, chat = await _chat_with_entry(client)
    actor = await create_user(organization_id=chat.organization_id)
    async with chat.workspace.record(EventAction.CHAT_RENAMED, recordable=chat, creator_id=actor.id) as rec:
        rec.event.details.update({"title": "Launch war room"})
    await Mailbox.sync(chat)

    item = {i["id"]: i for i in (await client.get("/api/mailbox_entries?view=inbox")).json()["entries"]}[str(entry.id)]
    assert item["chat"]["preview_kind"] == "activity"
    assert item["chat"]["last_comment"] is None
    assert item["chat"]["event_action"] == "chat_renamed"
    assert item["chat"]["event_details"]["title"] == "Launch war room"
    assert item["chat"]["event_actor"]["id"] == str(actor.id)


@pytest.mark.asyncio
async def test_list_returns_is_snoozed_false_when_snooze_expired(client: AppClient):
    # An entry whose snoozed_until is in the past (between expiry and the next
    # CheckSnoozedMailboxEntriesJob tick) must report is_snoozed=False at request
    # time — the model property `is_snoozed` is non-time-aware on purpose, so the
    # API computes a time-aware view via _is_snoozed_now.
    entry, _ = await _chat_with_entry(client)
    entry.snoozed_until = datetime.now(UTC) - timedelta(hours=1)
    await entry.save(update_fields=["snoozed_until"])

    response = await client.get("/api/mailbox_entries?view=inbox")
    items = {item["id"]: item for item in response.json()["entries"]}
    assert items[str(entry.id)]["is_snoozed"] is False


@pytest.mark.asyncio
async def test_list_inbox_returns_email_thread_entries(client: AppClient):
    entry, thread = await _email_thread_with_entry(client)

    response = await client.get("/api/mailbox_entries?view=inbox")
    assert response.status_code == status.HTTP_200_OK
    items = {item["id"]: item for item in response.json()["entries"]}

    item = items[str(entry.id)]
    assert item["resource_type"] == "EmailThread"
    assert item["email"] is not None
    assert item["email"]["sender_display"]
    # A thread with only messages previews the mail snippet on the top-level `preview`.
    assert item["email"]["preview_kind"] == "message"
    assert item["sender_display"] == item["email"]["sender_display"]
    assert item["href"] == f"/email_threads/{thread.id}?mailbox_entry_id={entry.id}"


@pytest.mark.asyncio
async def test_list_drafts_surfaces_scheduled_for(client: AppClient):
    user = await client.get_default_user()

    scheduled_for = datetime.now(UTC) + timedelta(days=1)
    scheduled_draft = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.DRAFT,
        labels=[EmailLabel.DRAFT],
        subject="Scheduled",
        scheduled_for=scheduled_for,
    )
    plain_draft = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.DRAFT,
        labels=[EmailLabel.DRAFT],
        subject="Plain",
    )
    for message in (scheduled_draft, plain_draft):
        await Mailbox.sync(await EmailThread.get(id=message.thread_id))

    scheduled_entry = await MailboxEntry.get(
        resource_gid=str((await EmailThread.get(id=scheduled_draft.thread_id)).global_id), owner_id=user.id
    )
    plain_entry = await MailboxEntry.get(
        resource_gid=str((await EmailThread.get(id=plain_draft.thread_id)).global_id), owner_id=user.id
    )

    response = await client.get("/api/mailbox_entries?view=drafts")
    assert response.status_code == status.HTTP_200_OK
    items = {item["id"]: item for item in response.json()["entries"]}

    # scheduled_for is read off the already-prefetched thread messages — no per-row
    # query — so a whole page of drafts resolves their scheduled state at once.
    assert items[str(scheduled_entry.id)]["email"]["scheduled_for"] is not None
    assert items[str(plain_entry.id)]["email"]["scheduled_for"] is None


@pytest.mark.asyncio
async def test_list_inbox_email_preview_message_comment_activity(client: AppClient):
    # Email's asymmetric three-way (email/mailbox.py): a message snippet by default, a comment
    # newer than the last message as an authored chip, and an activity event (collaborator add)
    # newer than both message and comment as a client-phrased line. The message/comment path is
    # the pre-existing behaviour; only the activity branch is new.
    user = await client.get_default_user()
    entry, thread = await _email_thread_with_entry(client)
    await thread.fetch_related("workspace")

    async def email_detail() -> dict:
        response = await client.get("/api/mailbox_entries?view=inbox")
        items = {item["id"]: item for item in response.json()["entries"]}
        return items[str(entry.id)]["email"]

    detail = await email_detail()
    assert detail["preview_kind"] == "message"

    await create_email_thread_comment(email_thread_id=thread.id, user_id=user.id, content="Team, thoughts?")
    await EmailMailboxEntry(email_thread=thread).touch(user)
    detail = await email_detail()
    assert detail["preview_kind"] == "comment"
    assert detail["last_comment"] == "Team, thoughts?"

    admin = await create_user(organization_id=user.organization_id, is_admin=True)
    async with thread.workspace.record(EventAction.ADDED_COLLABORATOR, creator_id=admin.id) as rec:
        rec.event.details = {"collaborator": admin.field_values}
    await EmailMailboxEntry(email_thread=thread).touch(user)
    detail = await email_detail()
    assert detail["preview_kind"] == "activity"
    assert detail["event_action"] == "added_collaborator"
    assert detail["event_actor"]["id"] == str(admin.id)


@pytest.mark.asyncio
async def test_list_inbox_returns_post_entries(client: AppClient):
    entry, post = await _post_with_entry(client)

    response = await client.get("/api/mailbox_entries?view=inbox")
    assert response.status_code == status.HTTP_200_OK
    items = {item["id"]: item for item in response.json()["entries"]}

    item = items[str(entry.id)]
    assert item["resource_type"] == "Post"
    assert item["post"] is not None
    assert item["post"]["is_announcement"] is False
    assert item["post"]["creator_name"] == (await post.creator).display_name
    assert item["post"]["group_name"] is None
    assert item["href"].startswith(f"/posts/{post.id}")


@pytest.mark.asyncio
async def test_list_inbox_serializes_post_comment(client: AppClient):
    # A discussion comment is an authored case: its text rides last_comment with the author
    # (preview_kind "comment"), rendered as a plain preview line led by the author's avatar.
    entry, post = await _post_with_entry(client)
    commenter = await create_user(organization_id=post.organization_id)
    comment = PostComment(post_id=post.id, user_id=commenter.id, content="Looks great")
    async with post.workspace.record(EventAction.POST_COMMENTED, recordable=comment, creator_id=commenter.id) as rec:
        await comment.save(rec.using_db)
    await PostMailboxEntry(post).sync(event=rec.event, direct_recipients=[])

    item = {i["id"]: i for i in (await client.get("/api/mailbox_entries?view=inbox")).json()["entries"]}[str(entry.id)]
    assert item["post"]["preview_kind"] == "comment"
    assert item["post"]["last_comment"] == "Looks great"
    assert item["post"]["last_comment_author"]["id"] == str(commenter.id)


@pytest.mark.asyncio
async def test_list_inbox_serializes_post_created_original_comment(client: AppClient):
    # A freshly published post previews its body — the original comment — rather than a bare
    # "Posted" activity line. The body rides last_comment authored by the post's creator.
    entry, post = await _post_with_entry(client)
    await post.fetch_related("comments")
    original = post.original_comment
    async with post.workspace.record(EventAction.POST_CREATED, recordable=post, creator_id=post.creator_id) as rec:
        pass
    await PostMailboxEntry(post).sync(event=rec.event, direct_recipients=[])

    item = {i["id"]: i for i in (await client.get("/api/mailbox_entries?view=inbox")).json()["entries"]}[str(entry.id)]
    assert item["post"]["preview_kind"] == "comment"
    assert item["post"]["last_comment"] == original.content
    assert item["post"]["last_comment_author"]["id"] == str(post.creator_id)


@pytest.mark.asyncio
async def test_list_inbox_serializes_post_activity_event(client: AppClient):
    # A non-authored event ships as raw action + Event diff (no phrased string) for the client to
    # render the "activity" line itself.
    entry, post = await _post_with_entry(client)
    admin = await create_user(organization_id=post.organization_id, is_admin=True)
    async with post.workspace.record(EventAction.POST_PINNED, creator_id=admin.id) as rec:
        pass
    await PostMailboxEntry(post).sync(event=rec.event, direct_recipients=[])

    item = {i["id"]: i for i in (await client.get("/api/mailbox_entries?view=inbox")).json()["entries"]}[str(entry.id)]
    assert item["post"]["preview_kind"] == "activity"
    assert item["post"]["last_comment"] is None
    assert item["post"]["event_action"] == "post_pinned"
    assert item["post"]["event_actor"]["id"] == str(admin.id)


@pytest.mark.asyncio
async def test_list_inbox_returns_goal_entries(client: AppClient):
    # Regression: a registered GoalMailboxEntry emits resource_type "Goal". The list
    # endpoint must serialize it (not 500 on an unknown type and blank the whole inbox).
    entry, goal = await _goal_with_entry(client)

    response = await client.get("/api/mailbox_entries?view=inbox")
    assert response.status_code == status.HTTP_200_OK
    items = {item["id"]: item for item in response.json()["entries"]}

    item = items[str(entry.id)]
    assert item["resource_type"] == "Goal"
    assert item["title"] == "Ship Q3"
    assert item["preview"] == "Improve onboarding conversion"
    assert item["goal"] is not None
    # Evergreen state read live off the goal.
    assert item["goal"]["status"] == "on_track"
    assert item["goal"]["is_completed"] is False
    assert item["goal"]["progress"] == 0.5
    # Latest event is the comment, so the second line is the comment body with its author.
    assert item["goal"]["preview_kind"] == "comment"
    assert item["goal"]["last_comment"] == "Kicking this off"
    assert item["goal"]["last_comment_author"] is not None
    assert item["href"].startswith(f"/goals/{goal.id}")
    assert f"mailbox_entry_id={entry.id}" in item["href"]


@pytest.mark.asyncio
async def test_list_inbox_serializes_goal_activity_event(client: AppClient):
    # A non-authored event ships as raw action + Event diff (no phrased string), so the client
    # can render the "activity" line itself. Supersede the comment with a status change.
    entry, goal = await _goal_with_entry(client)
    async with goal.workspace.record(EventAction.GOAL_UPDATED, creator_id=goal.owner_id) as rec:
        rec.event.details["status"] = [GoalStatus.ON_TRACK.value, GoalStatus.OFF_TRACK.value]
    await GoalMailboxEntry(goal).sync(event=rec.event, direct_recipients=[])

    response = await client.get("/api/mailbox_entries?view=inbox")
    assert response.status_code == status.HTTP_200_OK
    item = {i["id"]: i for i in response.json()["entries"]}[str(entry.id)]

    assert item["goal"]["preview_kind"] == "activity"
    assert item["goal"]["last_comment"] is None
    assert item["goal"]["event_action"] == "goal_updated"
    assert item["goal"]["event_details"]["status"] == ["on_track", "off_track"]
    assert item["goal"]["event_actor"]["id"] == str(goal.owner_id)


@pytest.mark.asyncio
async def test_list_archived_view(client: AppClient):
    entry, _ = await _chat_with_entry(client)
    mailbox = Mailbox(user=await client.get_default_user())
    chat = await Chat.get(id=entry.resource_gid.record_id)
    await mailbox.archive(chat)

    inbox = await client.get("/api/mailbox_entries?view=inbox")
    archived = await client.get("/api/mailbox_entries?view=archived")
    assert all(item["id"] != str(entry.id) for item in inbox.json()["entries"])
    archived_ids = {item["id"] for item in archived.json()["entries"]}
    assert str(entry.id) in archived_ids


@pytest.mark.asyncio
async def test_list_snoozed_view(client: AppClient):
    entry, _ = await _chat_with_entry(client)
    mailbox = Mailbox(user=await client.get_default_user())
    chat = await Chat.get(id=entry.resource_gid.record_id)
    await mailbox.snooze(chat, snoozed_until=datetime.now(UTC) + timedelta(hours=1))

    snoozed = await client.get("/api/mailbox_entries?view=snoozed")
    response_ids = {item["id"] for item in snoozed.json()["entries"]}
    assert str(entry.id) in response_ids


@pytest.mark.asyncio
async def test_list_assigned_to_me_filters_by_assignee(client: AppClient):
    entry, _ = await _chat_with_entry(client)
    user = await client.get_default_user()
    entry.assignee_id = user.id
    await entry.save(update_fields=["assignee_id"])

    response = await client.get("/api/mailbox_entries?view=assigned_to_me")
    items = response.json()["entries"]
    assert any(item["id"] == str(entry.id) and item["is_assigned_to_me"] for item in items)


@pytest.mark.asyncio
async def test_list_inbox_sort_oldest(client: AppClient):
    user = await client.get_default_user()
    entry_old, _ = await _chat_with_entry(client)
    entry_old.last_activity_at = datetime.now(UTC) - timedelta(days=2)
    await entry_old.save(update_fields=["last_activity_at"])

    other = await create_user(organization_id=user.organization_id)
    chat2 = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=other.id)
    await create_chat_message(chat_id=chat2.id, user_id=other.id, content="More recent")
    await chat2.refresh_from_db()
    await Mailbox.sync(chat2)

    newest = await client.get("/api/mailbox_entries?view=inbox&sort=newest")
    oldest = await client.get("/api/mailbox_entries?view=inbox&sort=oldest")

    newest_ids = [item["id"] for item in newest.json()["entries"]]
    oldest_ids = [item["id"] for item in oldest.json()["entries"]]
    assert oldest_ids[0] == str(entry_old.id)
    assert newest_ids != oldest_ids


@pytest.mark.asyncio
async def test_list_unread_view(client: AppClient):
    user = await client.get_default_user()
    unread_entry, _ = await _chat_with_entry(client)
    assert unread_entry.is_unread

    other = await create_user(organization_id=user.organization_id)
    chat2 = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=other.id)
    await create_chat_message(chat_id=chat2.id, user_id=other.id, content="hi")
    await chat2.refresh_from_db()
    await Mailbox.sync(chat2)
    read_entry = await MailboxEntry.get(resource_gid=str(chat2.global_id), owner_id=user.id)
    await read_entry.mark_as_read()

    async def ids_for(view: str) -> set[str]:
        response = await client.get(f"/api/mailbox_entries?view={view}")
        return {item["id"] for item in response.json()["entries"]}

    assert {str(unread_entry.id), str(read_entry.id)} <= await ids_for("inbox")

    unread_ids = await ids_for("unread")
    assert str(unread_entry.id) in unread_ids
    assert str(read_entry.id) not in unread_ids


@pytest.mark.asyncio
async def test_list_pagination(client: AppClient):
    user = await client.get_default_user()
    other = await create_user(organization_id=user.organization_id)
    per_page = settings.pagination_default_per_page
    for _ in range(per_page + 1):
        chat = await create_chat(organization_id=user.organization_id)
        await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
        await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)
        await create_chat_message(chat_id=chat.id, user_id=other.id, content="hi")
        await chat.refresh_from_db()
        await Mailbox.sync(chat)

    page1 = await client.get("/api/mailbox_entries?view=inbox")
    body1 = page1.json()
    assert body1["has_more"] is True
    assert body1["next_cursor"] is not None
    assert len(body1["entries"]) == per_page

    page2 = await client.get(f"/api/mailbox_entries?view=inbox&cursor={body1['next_cursor']}")
    body2 = page2.json()
    assert body2["has_more"] is False
    assert len(body2["entries"]) == 1
    page1_ids = {item["id"] for item in body1["entries"]}
    assert all(item["id"] not in page1_ids for item in body2["entries"])


@pytest.mark.asyncio
async def test_lookup_returns_only_requested_entries(client: AppClient):
    # The lookup endpoint backs the mailbox-views React island: sections
    # reference entries by id only, and the client hydrates them in one request.
    entry_a, _ = await _chat_with_entry(client)
    entry_b, _ = await _chat_with_entry(client)
    entry_c, _ = await _chat_with_entry(client)

    response = await client.get(f"/api/mailbox_entries/lookup?ids={entry_a.id}&ids={entry_c.id}")
    assert response.status_code == status.HTTP_200_OK
    # Serves mutable read/archived state; no-store keeps back/forward navigation
    # from re-hydrating sections with a stale snapshot (see issue #8343).
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    ids = {item["id"] for item in body["entries"]}
    assert ids == {str(entry_a.id), str(entry_c.id)}
    assert str(entry_b.id) not in ids


@pytest.mark.asyncio
async def test_lookup_excludes_foreign_entries(client: AppClient):
    # Section ids originate from LLM output; a hallucinated/tampered id pointing at another
    # user's (and org's) entry must not hydrate. The endpoint is scoped to the requester's
    # inbox (by_owner), so a foreign id is silently dropped rather than leaked.
    mine, _ = await _chat_with_entry(client)

    stranger = await create_user()
    stranger_chat = await create_chat(organization_id=stranger.organization_id)
    await create_collaborator(workspace_id=stranger_chat.workspace_id, user_id=stranger.id)
    await create_chat_message(chat_id=stranger_chat.id, user_id=stranger.id, content="Private")
    await Mailbox.sync(stranger_chat)
    foreign = await MailboxEntry.get(resource_gid=str(stranger_chat.global_id), owner_id=stranger.id)

    response = await client.get(f"/api/mailbox_entries/lookup?ids={mine.id}&ids={foreign.id}")
    assert response.status_code == status.HTTP_200_OK
    ids = {item["id"] for item in response.json()["entries"]}
    assert ids == {str(mine.id)}
    assert str(foreign.id) not in ids


@pytest.mark.asyncio
async def test_lookup_rejects_malformed_ids(client: AppClient):
    # FastAPI validates `list[UUID]` at the boundary — a non-UUID value fails
    # request validation rather than being silently dropped.
    entry, _ = await _chat_with_entry(client)

    response = await client.get(f"/api/mailbox_entries/lookup?ids={entry.id}&ids=not-a-uuid")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
