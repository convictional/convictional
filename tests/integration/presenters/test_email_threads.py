import pytest

from app.models.collaboration.mailbox import MailboxEntry
from app.models.workspaces.chat import Chat, ChatMailboxEntry
from app.models.workspaces.email.mailbox import EmailMailboxEntry
from app.models.workspaces.goals import Goal
from app.models.workspaces.posts import Post
from app.presenters.mailbox_entries import MailboxEntryPresenter
from infra.db import GlobalID
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_collaborator,
    create_email_message,
    create_email_thread,
    create_goal,
    create_mailbox_entry,
    create_post,
    create_user,
)


@pytest.mark.asyncio
async def test_mailbox_entry_presenter_sender_display():
    user = await create_user(email="owner@example.com")

    thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Alice Smith <alice@example.com>",
        to=["owner@example.com"],
        subject="Project Conversation",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Bob Johnson <bob@example.com>",
        to=["owner@example.com", "alice@example.com"],
        subject="Re: Project Conversation",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Alice Smith <alice@example.com>",
        to=["owner@example.com", "bob@example.com"],
        subject="Project Conversation",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Charlie Davis <charlie@example.com>",
        to=["owner@example.com", "alice@example.com", "bob@example.com"],
        subject="Re: Project Conversation",
    )

    # Create mailbox entry for the thread
    mailbox_entry = await create_mailbox_entry(organization_id=user.organization_id, resource_gid=thread.global_id)
    await mailbox_entry.fetch_related("owner")

    await thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    # Sync the mailbox entry from the email thread to populate senders
    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(mailbox_entry)

    presenter = MailboxEntryPresenter.create(mailbox_entry)
    presenter.resource = thread

    # Should show first and last senders: Alice (first) and Charlie (last)
    assert presenter.original_sender
    assert presenter.most_recent_sender
    assert presenter.original_sender.email == "alice@example.com"  # first sender
    assert presenter.original_sender.name == "Alice Smith"
    assert presenter.most_recent_sender.email == "charlie@example.com"  # last sender
    assert presenter.most_recent_sender.name == "Charlie Davis"
    assert presenter.additional_sender_count == 1  # 1 sender in between (Bob Johnson)


@pytest.mark.asyncio
async def test_mailbox_entry_presenter_same_email_different_names():
    user = await create_user(email="owner@example.com")

    thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)

    # Same email address but different display names
    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="John Smith <john@example.com>",
        to=["owner@example.com"],
        subject="Initial Message",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="J. Smith <john@example.com>",
        to=["owner@example.com"],
        subject="Re: Initial Message",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Johnny <john@example.com>",
        to=["owner@example.com"],
        subject="Re: Initial Message",
    )

    # Create mailbox entry for the thread
    mailbox_entry = await create_mailbox_entry(organization_id=user.organization_id, resource_gid=thread.global_id)
    await mailbox_entry.fetch_related("owner")

    await thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    # Sync the mailbox entry from the email thread to populate senders
    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(mailbox_entry)

    presenter = MailboxEntryPresenter.create(mailbox_entry)
    presenter.resource = thread

    # Should show first and last senders with their respective display names
    assert presenter.original_sender
    assert presenter.most_recent_sender
    assert presenter.original_sender.email == "john@example.com"
    assert presenter.original_sender.name == "John Smith"  # first display name
    assert presenter.most_recent_sender.email == "john@example.com"
    assert presenter.most_recent_sender.name == "Johnny"  # last display name
    assert presenter.additional_sender_count == 1  # 1 sender in between (J. Smith)


@pytest.mark.asyncio
async def test_mailbox_entry_presenter_same_sender_first_and_last():
    """Test that most recent sender shows correctly when same as first sender."""
    user = await create_user(email="owner@example.com")
    thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Alice Smith <alice@example.com>",
        to=["owner@example.com"],
        subject="Project Conversation",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Bob Johnson <bob@example.com>",
        to=["owner@example.com", "alice@example.com"],
        subject="Re: Project Conversation",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Alice Smith <alice@example.com>",
        to=["owner@example.com", "bob@example.com"],
        subject="Re: Project Conversation",
    )

    mailbox_entry = await create_mailbox_entry(organization_id=user.organization_id, resource_gid=thread.global_id)
    await mailbox_entry.fetch_related("owner")

    await thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(mailbox_entry)

    presenter = MailboxEntryPresenter.create(mailbox_entry)
    presenter.resource = thread

    # Original sender is Alice (first message)
    assert presenter.original_sender
    assert presenter.original_sender.email == "alice@example.com"
    assert presenter.original_sender.name == "Alice Smith"

    # Most recent sender should be Alice (last message), NOT Bob
    assert presenter.most_recent_sender
    assert presenter.most_recent_sender.email == "alice@example.com"
    assert presenter.most_recent_sender.name == "Alice Smith"

    # Additional sender count is 1 because we only show Alice (who is both first and last)
    # so Bob counts as 1 additional hidden sender
    assert presenter.additional_sender_count == 1


@pytest.mark.asyncio
async def test_mailbox_entry_presenter_skips_current_user_as_most_recent():
    """Test that most recent sender skips the current user."""
    user = await create_user(email="owner@example.com")
    thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Alice Smith <alice@example.com>",
        to=["owner@example.com"],
        subject="Project Conversation",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Bob Johnson <bob@example.com>",
        to=["owner@example.com", "alice@example.com"],
        subject="Re: Project Conversation",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Owner <owner@example.com>",
        to=["alice@example.com", "bob@example.com"],
        subject="Re: Project Conversation",
    )

    mailbox_entry = await create_mailbox_entry(organization_id=user.organization_id, resource_gid=thread.global_id)
    await mailbox_entry.fetch_related("owner")

    await thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(mailbox_entry)

    presenter = MailboxEntryPresenter.create(mailbox_entry, current_user_email="owner@example.com")
    presenter.resource = thread

    assert presenter.original_sender
    assert presenter.original_sender.email == "alice@example.com"

    # Most recent sender should be Bob (skipping the current user who sent last)
    assert presenter.most_recent_sender
    assert presenter.most_recent_sender.email == "bob@example.com"
    assert presenter.most_recent_sender.name == "Bob Johnson"


@pytest.mark.asyncio
async def test_mailbox_entry_presenter_hides_duplicate_when_single_sender():
    """Test that when only one unique sender, most_recent is None to avoid 'Name, Name' display."""
    user = await create_user(email="owner@example.com")
    thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Owner <owner@example.com>",
        to=["alice@example.com"],
        subject="Initial Message",
    )

    await create_email_message(
        organization_id=user.organization_id,
        creator_id=user.id,
        external_thread_id=thread.external_thread_id,
        sender="Owner <owner@example.com>",
        to=["alice@example.com"],
        subject="Follow Up",
    )

    mailbox_entry = await create_mailbox_entry(organization_id=user.organization_id, resource_gid=thread.global_id)
    await mailbox_entry.fetch_related("owner")

    await thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(mailbox_entry)

    presenter = MailboxEntryPresenter.create(mailbox_entry, current_user_email="owner@example.com")
    presenter.resource = thread

    assert presenter.original_sender
    assert presenter.original_sender.email == "owner@example.com"

    # most_recent should be None when same as original and no other senders
    assert presenter.most_recent_sender is None
    assert presenter.count_senders == 1


@pytest.mark.asyncio
async def test_load_resources_populates_resource_on_presenters():
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, title="Q1 Revenue")
    goal_gid = GlobalID.create("Goal", goal.id)

    entry_with_resource = await create_mailbox_entry(
        organization_id=user.organization_id,
        owner_id=user.id,
        resource_gid=str(goal_gid),
    )
    entry_without_resource = await create_mailbox_entry(
        organization_id=user.organization_id,
        owner_id=user.id,
    )

    # Deleted goal to verify missing resources return None
    deleted_goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, title="Deleted Goal")
    deleted_goal_gid = GlobalID.create("Goal", deleted_goal.id)
    entry_with_deleted_resource = await create_mailbox_entry(
        organization_id=user.organization_id,
        owner_id=user.id,
        resource_gid=str(deleted_goal_gid),
    )
    await deleted_goal.delete()

    presenters = await MailboxEntryPresenter.create_from_list(
        [entry_with_resource, entry_without_resource, entry_with_deleted_resource]
    )

    assert presenters[0].resource is not None
    assert isinstance(presenters[0].resource, Goal)
    assert presenters[0].resource.id == goal.id
    assert presenters[1].resource is None
    assert presenters[2].resource is None


@pytest.mark.asyncio
async def test_load_resources_excludes_resources_user_cannot_access():
    org_a_user = await create_user()
    org_b_user = await create_user()
    assert org_a_user.organization_id != org_b_user.organization_id

    goal = await create_goal(
        organization_id=org_a_user.organization_id,
        creator_id=org_a_user.id,
        title="Org A Confidential Goal",
    )
    goal_gid = GlobalID.create("Goal", goal.id)

    entry_a = await create_mailbox_entry(
        organization_id=org_a_user.organization_id,
        owner_id=org_a_user.id,
        resource_gid=str(goal_gid),
    )
    entry_b = await create_mailbox_entry(
        organization_id=org_b_user.organization_id,
        owner_id=org_b_user.id,
        resource_gid=str(goal_gid),
    )

    presenters_a = await MailboxEntryPresenter.create_from_list([entry_a])
    assert presenters_a[0].resource is not None
    assert presenters_a[0].resource.id == goal.id

    presenters_b = await MailboxEntryPresenter.create_from_list([entry_b])
    assert presenters_b[0].resource is None, "Cross-org user should not see another org's resource"


@pytest.mark.asyncio
async def test_load_resources_for_post():
    user = await create_user()
    post = await create_post(organization_id=user.organization_id, creator_id=user.id, title="Team Discussion")
    post_gid = GlobalID.create("Post", post.id)

    entry = await create_mailbox_entry(
        organization_id=user.organization_id,
        owner_id=user.id,
        resource_gid=str(post_gid),
    )

    presenters = await MailboxEntryPresenter.create_from_list([entry])

    assert presenters[0].resource is not None
    assert isinstance(presenters[0].resource, Post)
    assert presenters[0].resource.id == post.id
    assert presenters[0].resource.title == "Team Discussion"


@pytest.mark.asyncio
async def test_load_resources_for_chat_with_counterparty():
    user_a = await create_user()
    user_b = await create_user(organization_id=user_a.organization_id)

    chat = await create_chat(organization_id=user_a.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_a.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_b.id)
    await create_chat_message(chat_id=chat.id, user_id=user_b.id, content="Hey")
    await chat.refresh_from_db()

    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_a.id)

    presenters = await MailboxEntryPresenter.create_from_list([entry])
    presenter = presenters[0]

    assert isinstance(presenter.resource, Chat)
    assert presenter.is_direct_message is True
    assert presenter.is_group_chat is False
    assert presenter.chat_counterparty is not None
    assert presenter.chat_counterparty.id == user_b.id
