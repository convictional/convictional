from datetime import UTC, datetime

import pytest

from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.collaboration.workspace import Attachment, Collaborator, SubscriberResolver
from app.models.workspaces.email.mailbox import EmailMailboxEntry
from app.models.workspaces.email.thread import EmailAttachment, EmailMessage, EmailThread, EmailThreadComment
from config.enums import EmailLabel, EmailMailboxLabel, EmailMessageType, EventAction, MailboxLabel
from infra.storage import FileReference
from tests.helpers.factories import (
    create_collaborator,
    create_email_message,
    create_email_thread,
    create_mailbox_entry,
    create_organization,
    create_user,
)


@pytest.mark.asyncio
async def test_sync_from_email_thread_creates_new_mailbox_entry():
    organization = await create_organization()
    email_creator = await create_user(organization_id=organization.id)
    inbox_owner = await create_user(organization_id=organization.id)
    assignee = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(
        creator_id=email_creator.id,
        organization_id=organization.id,
        external_thread_id="test_thread_1",
        title="Test Email Thread",
        labels=[EmailLabel.INBOX, EmailLabel.SENT],
    )

    # Add comment from email creator so inbox owner sees it as "by others"
    comment = EmailThreadComment(
        email_thread_id=email_thread.id, user_id=email_creator.id, content="Test comment from email creator"
    )
    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=email_creator.id
    ) as recording:
        await comment.save(recording.using_db)

    await email_thread.fetch_related("comments", "messages__attachments")

    # Add inbox_owner as a collaborator
    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=inbox_owner.id)

    # Set an assignee on the workspace to test assignee syncing
    email_thread.workspace.assignee = assignee
    await email_thread.workspace.save()

    # Test the sync method
    await email_thread.fetch_related(
        "workspace__collaborators__user",
        "workspace__events",
        "comments",
        "workspace__attachments",
        "messages__attachments",
    )
    mailbox_sync = await EmailMailboxEntry(email_thread).refresh_row_and_mark_unread(inbox_owner)
    assert mailbox_sync is not None
    assert mailbox_sync.user_id == inbox_owner.id
    mailbox_entry = await MailboxEntry.get(id=mailbox_sync.entry_id)
    assert mailbox_entry.resource_gid == email_thread.global_id
    assert mailbox_entry.owner_id == inbox_owner.id
    assert mailbox_entry.organization_id == organization.id

    # Test field syncing
    assert mailbox_entry.title == email_thread.title
    assert mailbox_entry.is_shared is True  # created by different user than owner
    assert mailbox_entry.last_comment == "Test comment from email creator"
    assert mailbox_entry.last_comment_author_id == email_creator.id
    assert mailbox_entry.assignee_id == assignee.id  # Test assignee syncing

    assert mailbox_entry.workspace_attachment_count == 0

    # Test label inheritance - should inherit original labels plus INBOX and UNREAD
    # SENT label is removed for shared threads (created by different user than owner)
    assert MailboxLabel.INBOX in mailbox_entry.labels
    assert MailboxLabel.UNREAD in mailbox_entry.labels
    assert EmailMailboxLabel.SENT not in mailbox_entry.labels


@pytest.mark.asyncio
async def test_sync_from_email_thread_updates_existing_mailbox_entry():
    organization = await create_organization()
    email_creator = await create_user(organization_id=organization.id)
    inbox_owner = await create_user(organization_id=organization.id)
    commenter = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(
        creator_id=email_creator.id,
        organization_id=organization.id,
        external_thread_id="test_thread_2",
        title="Updated Email Thread Title",
        labels=[EmailLabel.DRAFT],
    )

    # Create existing mailbox entry with old data
    existing_inbox = await create_mailbox_entry(
        resource_gid=email_thread.global_id,
        owner_id=inbox_owner.id,
        organization_id=organization.id,
        title="Old Title",
        preview="Old preview",
        last_comment="Old comment",
        last_comment_author_id=inbox_owner.id,
        senders=["old@example.com"],
        labels=[EmailMailboxLabel.SPAM],
    )

    # Add new comment from different user
    comment = EmailThreadComment(
        email_thread_id=email_thread.id, user_id=commenter.id, content="New comment from commenter"
    )
    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=commenter.id
    ) as recording:
        await comment.save(recording.using_db)

    await email_thread.fetch_related("comments", "messages__attachments")

    # Add inbox_owner as a collaborator
    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=inbox_owner.id)

    # Test the sync method
    await email_thread.fetch_related(
        "workspace__collaborators__user",
        "workspace__events",
        "comments",
        "workspace__attachments",
        "messages__attachments",
    )
    updated_inbox = await EmailMailboxEntry(email_thread).refresh_row_and_mark_unread(inbox_owner)
    assert updated_inbox is not None
    assert updated_inbox.entry_id == existing_inbox.id

    # Test field updates
    await existing_inbox.refresh_from_db()
    assert existing_inbox.title == "Updated Email Thread Title"
    assert existing_inbox.last_comment == "New comment from commenter"
    assert existing_inbox.last_comment_author_id == commenter.id

    assert existing_inbox.workspace_attachment_count == 0

    # Test label updates - should add INBOX and UNREAD due to changes
    assert MailboxLabel.INBOX in existing_inbox.labels
    assert MailboxLabel.UNREAD in existing_inbox.labels
    # Should keep original SPAM label since labels aren't replaced for existing threads
    assert EmailMailboxLabel.SPAM in existing_inbox.labels


@pytest.mark.asyncio
async def test_email_no_event_sync_across_collaborators():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator1 = await create_user(organization_id=organization.id)
    collaborator2 = await create_user(organization_id=organization.id)
    former_collaborator = await create_user(organization_id=organization.id)
    email_message = await create_email_message(
        external_message_id="test_msg_multi",
        external_thread_id="test_thread_multi",
        subject="Multi-Collaborator Email Thread",
        sender="sender@example.com",
        to=["team@example.com"],
        body_plain="Test email content for multi-collaborator thread",
        organization_id=organization.id,
        user_id=owner.id,
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
    )
    await email_message.fetch_related("thread__workspace")
    email_thread = email_message.thread

    # Add all users as collaborators initially including former_collaborator
    async with email_thread.workspace.record(EventAction.ADDED_COLLABORATOR, creator_id=owner.id):
        await email_thread.collaboration.add(collaborator1, owner)
    async with email_thread.workspace.record(EventAction.ADDED_COLLABORATOR, creator_id=owner.id):
        await email_thread.collaboration.add(collaborator2, owner)
    async with email_thread.workspace.record(EventAction.ADDED_COLLABORATOR, creator_id=owner.id):
        await email_thread.collaboration.add(former_collaborator, owner)

    # Add a comment from collaborator1 to test last_comment sync
    comment = EmailThreadComment(
        email_thread_id=email_thread.id, user_id=collaborator1.id, content="Comment from collaborator1"
    )
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=collaborator1.id
    ) as recording:
        await comment.save(recording.using_db)

    # The no-event sync reaches every collaborator (force-included) and creates a row for each
    await EmailMailboxEntry(email_thread).sync()

    # Verify mailbox entries created for all collaborators (including creator and former_collaborator)
    mailbox_entries = await MailboxEntry.filter(
        MailboxEntry.filters.by_resource(email_thread.global_id),
    ).prefetch_related("owner")
    assert len(mailbox_entries) == 4  # owner, collaborator1, collaborator2, former_collaborator

    owner_ids = {entry.owner_id for entry in mailbox_entries}
    assert owner_ids == {owner.id, collaborator1.id, collaborator2.id, former_collaborator.id}

    # Test content synchronization for each mailbox entry
    for entry in mailbox_entries:
        assert entry.title == email_thread.title
        assert entry.resource_gid == email_thread.global_id
        assert entry.organization_id == email_thread.organization_id
        assert MailboxLabel.INBOX in entry.labels
        assert MailboxLabel.UNREAD in entry.labels

        assert entry.workspace_attachment_count == 0

        # Test is_shared flag: creator should have False, collaborators should have True
        if entry.owner_id == owner.id:
            assert not entry.is_shared  # Creator's own thread
        else:
            assert entry.is_shared  # Collaborator's shared thread

        # Test last_comment sync
        assert entry.last_comment == "Comment from collaborator1"
        assert entry.last_comment_author_id == collaborator1.id

    # Test mark_as_read/mark_as_unread on MailboxEntry
    owner_entry = next(entry for entry in mailbox_entries if entry.owner_id == owner.id)
    collaborator_entry = next(entry for entry in mailbox_entries if entry.owner_id == collaborator1.id)

    # All entries should be unread initially
    assert owner_entry.is_read is False
    assert owner_entry.read_at is None
    assert collaborator_entry.is_read is False
    assert collaborator_entry.read_at is None

    # Test mark_as_read
    await owner_entry.mark_as_read()
    assert owner_entry.is_read is True
    assert owner_entry.read_at is not None

    # Test mark_as_unread (explicit unread clears read_at — the read high-water mark)
    await owner_entry.mark_as_unread()
    assert owner_entry.is_read is False
    assert owner_entry.is_unread
    assert owner_entry.read_at is None

    # Test Mailbox.mark_as_read/unread instance methods
    owner_mailbox = Mailbox(user=owner)
    await owner_mailbox.mark_as_read(email_thread)
    await owner_entry.refresh_from_db()
    assert owner_entry.is_read is True
    assert owner_entry.read_at is not None
    await owner_mailbox.mark_as_unread(email_thread)
    await owner_entry.refresh_from_db()
    assert owner_entry.is_read is False
    assert owner_entry.read_at is None

    # Test clear_non_collaborators functionality by removing former_collaborator
    async with email_thread.workspace.record(EventAction.REMOVED_COLLABORATOR, creator_id=owner.id):
        await email_thread.collaboration.remove(former_collaborator)

    # Sync again to test clear_non_collaborators
    await EmailMailboxEntry(email_thread).sync()

    # Verify former_collaborator's mailbox entry is removed but others remain
    active_mailbox_entries = await MailboxEntry.filter(
        MailboxEntry.filters.by_resource(email_thread.global_id),
    ).prefetch_related("owner")
    assert len(active_mailbox_entries) == 3  # only owner, collaborator1, collaborator2

    active_owner_ids = {entry.owner_id for entry in active_mailbox_entries}
    assert active_owner_ids == {owner.id, collaborator1.id, collaborator2.id}
    assert former_collaborator.id not in active_owner_ids

    # Verify former_collaborator's mailbox entry is soft-deleted
    former_collab_inbox = await MailboxEntry.unscoped.get_or_none(
        resource_gid=str(email_thread.global_id), owner_id=former_collaborator.id
    )
    assert former_collab_inbox is not None
    assert former_collab_inbox.is_deleted

    # Test EmailThread deletion → mailbox entry soft deletion
    await email_thread.remove_message(email_message)

    # Sync after deletion
    await EmailMailboxEntry(email_thread).sync()

    # Verify EmailThread is soft-deleted
    await email_thread.refresh_from_db()
    assert email_thread.is_deleted

    # Verify all mailbox entry records are also soft-deleted
    mailbox_entries_after_delete = await MailboxEntry.unscoped.filter(
        MailboxEntry.filters.by_resource(email_thread.global_id),
    )
    assert len(mailbox_entries_after_delete) == 4  # Still 4 records but soft-deleted (including former)
    for entry in mailbox_entries_after_delete:
        await entry.refresh_from_db()
        assert entry.is_deleted

    # Test EmailThread restoration → mailbox entry restoration
    # Add a new message to restore the thread
    restore_message = EmailMessage(
        external_message_id="restore_msg_123",
        external_thread_id="test_thread_multi",
        subject="Thread Restored",
        sender="restore@example.com",
        to=["team@example.com"],
        body_plain="This restores the thread",
        user_id=owner.id,
        organization_id=organization.id,
        message_type=EmailMessageType.RECEIVED,
        thread_id=email_thread.id,
        labels=[EmailLabel.INBOX],
    )
    await restore_message.save()
    await email_thread.update_metadata_from_messages()

    # Sync after restoration - this should restore for current collaborators and clear non-collaborators
    await EmailMailboxEntry(email_thread).sync()

    # Verify EmailThread is restored (not deleted)
    await email_thread.refresh_from_db()
    assert not email_thread.is_deleted

    # Verify only current collaborators' mailbox entry records are restored
    mailbox_entries_after_restore = await MailboxEntry.filter(MailboxEntry.filters.by_resource(email_thread.global_id))
    assert len(mailbox_entries_after_restore) == 3  # Only current collaborators restored
    for entry in mailbox_entries_after_restore:
        await entry.refresh_from_db()
        assert not entry.is_deleted
        # Should be marked as unread due to restoration changes
        assert MailboxLabel.UNREAD in entry.labels

    # Verify former_collaborator's mailbox entry remains soft-deleted even after restoration
    former_collab_inbox_after_restore = await MailboxEntry.unscoped.get_or_none(
        resource_gid=str(email_thread.global_id), owner_id=former_collaborator.id
    )
    assert former_collab_inbox_after_restore is not None
    assert former_collab_inbox_after_restore.is_deleted


@pytest.mark.asyncio
async def test_refresh_row_and_mark_unread_deletes_mailbox_entry_when_user_not_collaborator():
    organization = await create_organization()
    email_creator = await create_user(organization_id=organization.id)
    inbox_owner = await create_user(organization_id=organization.id)
    non_collaborator = await create_user(organization_id=organization.id)

    # Create EmailThread
    email_thread = await create_email_thread(
        creator_id=email_creator.id,
        organization_id=organization.id,
        external_thread_id="test_thread_removal",
        title="Test Thread for Removal",
        labels=[EmailLabel.INBOX],
    )

    # Add inbox_owner as a collaborator and create mailbox entry
    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=inbox_owner.id)
    await email_thread.fetch_related(
        "workspace__collaborators__user",
        "workspace__events",
        "comments",
        "workspace__attachments",
        "messages__attachments",
    )
    mailbox_sync = await EmailMailboxEntry(email_thread).refresh_row_and_mark_unread(inbox_owner)
    assert mailbox_sync is not None

    # Test non-collaborator returns None without creating mailbox entry
    await email_thread.fetch_related(
        "workspace__collaborators__user",
        "workspace__events",
        "comments",
        "workspace__attachments",
        "messages__attachments",
    )
    result = await EmailMailboxEntry(email_thread).refresh_row_and_mark_unread(non_collaborator)
    assert result is None
    gid = str(email_thread.global_id)
    assert await MailboxEntry.get_or_none(resource_gid=gid, owner_id=non_collaborator.id) is None

    # Remove collaborator and verify mailbox entry gets deleted
    collaborator = await Collaborator.get(workspace_id=email_thread.workspace_id, user_id=inbox_owner.id)
    await collaborator.delete()

    await email_thread.fetch_related(
        "workspace__collaborators__user",
        "workspace__events",
        "comments",
        "workspace__attachments",
        "messages__attachments",
    )
    result = await EmailMailboxEntry(email_thread).refresh_row_and_mark_unread(inbox_owner)
    assert result is None
    assert await MailboxEntry.get_or_none(resource_gid=str(email_thread.global_id), owner_id=inbox_owner.id) is None


#
# Tests for syncing MailboxEntry state from EmailThread
#
#


@pytest.mark.asyncio
async def test_sync_from_field_syncing():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)
    assignee = await create_user(organization_id=organization.id)
    message = await create_email_message(
        subject="Test Email Thread",
        creator_id=owner.id,
        organization_id=organization.id,
        received_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
    )
    email_thread = await EmailThread.get(id=message.thread_id)
    await email_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    # Set assignee on workspace
    email_thread.workspace.assignee = assignee
    await email_thread.workspace.save()

    # Test basic field syncing for owner
    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
    )
    await owner_entry.fetch_related("owner")
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(owner_entry)

    assert owner_entry.title == email_thread.title
    assert owner_entry.preview == email_thread.preview
    assert owner_entry.last_activity_at == email_thread.last_message_at
    assert not owner_entry.is_shared
    assert owner_entry.assignee_id == assignee.id

    # Test shared thread detection for collaborator
    collaborator_entry = MailboxEntry(
        owner_id=collaborator.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
    )
    await collaborator_entry.fetch_related("owner")
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(collaborator_entry)

    assert collaborator_entry.is_shared
    assert collaborator_entry.assignee_id == assignee.id


@pytest.mark.asyncio
async def test_sync_from_comment_syncing():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    commenter = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Email Thread with Comment"
    )

    # Add comment from another user
    comment = EmailThreadComment(
        email_thread_id=email_thread.id, user_id=commenter.id, content="Test comment from another user"
    )
    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=commenter.id
    ) as recording:
        await comment.save(recording.using_db)

    # Refresh workspace to include comments and fetch messages
    await email_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    # Test owner sees comment from others
    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
    )
    await owner_entry.fetch_related("owner")
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(owner_entry)
    assert owner_entry.last_comment == "Test comment from another user"
    assert owner_entry.last_comment_author_id == commenter.id

    assert owner_entry.workspace_attachment_count == 0


@pytest.mark.asyncio
async def test_sync_from_state_syncing():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    message = await create_email_message(
        subject="Email Thread State Test",
        creator_id=owner.id,
        organization_id=organization.id,
        received_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
    )
    email_thread = await EmailThread.get(id=message.thread_id)
    await email_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
    )
    await entry.fetch_related("owner")

    # Test deletion state syncing
    email_thread.deleted_at = datetime.now(UTC)
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(entry)
    assert entry.is_deleted

    # Test restoration syncing
    email_thread.deleted_at = None
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(entry)
    assert not entry.is_deleted

    # Test activity timestamp syncing - message timestamp as latest
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(entry)
    assert entry.last_activity_at == email_thread.last_message_at

    # Test activity timestamp syncing - workspace event timestamp as latest
    comment = EmailThreadComment(
        email_thread_id=email_thread.id, user_id=owner.id, content="Dummy comment for event test"
    )
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=owner.id
    ) as recording:
        await comment.save(recording.using_db)

    # Get the most recent event and update its timestamp
    await email_thread.workspace.fetch_related("events")
    latest_event = max(email_thread.workspace.events, key=lambda e: e.created_at)
    latest_event.created_at = datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC)
    await latest_event.save()

    # Refresh the email_thread to pick up the updated event timestamp
    await email_thread.refresh_from_db()
    await email_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(entry)
    assert entry.last_activity_at == latest_event.created_at


@pytest.mark.asyncio
async def test_sync_from_label_syncing():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    #
    # Test owner label syncing for different thread types
    #
    #

    # Test inbox labeling
    inbox_thread = await create_email_thread(
        creator_id=owner.id,
        organization_id=organization.id,
        title="Inbox Thread",
        labels=[EmailLabel.INBOX],
    )
    await inbox_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=inbox_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],
    )
    await entry.fetch_related("owner")
    EmailMailboxEntry(inbox_thread)._refresh_content_and_mark_unread(entry)
    assert MailboxLabel.INBOX in entry.labels

    # Sync must not auto-strip INBOX based on thread label state — explicit user archive
    # (via entry.archive()) is the only path that removes INBOX. A thread with empty
    # labels can mean "user archived it" OR "label-union math just happens to lack INBOX"
    # (e.g. thread of only outgoing messages); sync can't tell them apart, so it leaves
    # the entry's INBOX alone.
    archived_thread = await create_email_thread(
        creator_id=owner.id,
        organization_id=organization.id,
        title="Archived Thread",
        labels=[],
    )
    await archived_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=archived_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[MailboxLabel.INBOX],
    )
    await entry.fetch_related("owner")
    EmailMailboxEntry(archived_thread)._refresh_content_and_mark_unread(entry)
    assert MailboxLabel.INBOX in entry.labels

    # Test sent labeling
    sent_thread = await create_email_thread(
        creator_id=owner.id,
        organization_id=organization.id,
        title="Sent Thread",
        labels=[EmailLabel.SENT],
    )
    await sent_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=sent_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],
    )
    await entry.fetch_related("owner")
    EmailMailboxEntry(sent_thread)._refresh_content_and_mark_unread(entry)
    assert EmailMailboxLabel.SENT in entry.labels

    # Test draft labeling
    draft_thread = await create_email_thread(
        creator_id=owner.id,
        organization_id=organization.id,
        title="Draft Thread",
        labels=[EmailLabel.DRAFT],
    )
    await draft_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=draft_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],
    )
    await entry.fetch_related("owner")
    EmailMailboxEntry(draft_thread)._refresh_content_and_mark_unread(entry)
    assert EmailMailboxLabel.DRAFT in entry.labels

    # Test spam labeling
    spam_thread = await create_email_thread(
        creator_id=owner.id,
        organization_id=organization.id,
        title="Spam Thread",
        labels=[EmailLabel.SPAM],
    )
    await spam_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=spam_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],
    )
    await entry.fetch_related("owner")
    EmailMailboxEntry(spam_thread)._refresh_content_and_mark_unread(entry)
    assert EmailMailboxLabel.SPAM in entry.labels

    #
    # Test unread syncing for owners
    #
    #

    # Test read thread
    read_thread = await create_email_thread(
        creator_id=owner.id,
        organization_id=organization.id,
        title="Read Thread",
        labels=[EmailLabel.INBOX],  # Start as read
    )
    await read_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=read_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[MailboxLabel.UNREAD],
    )
    await entry.fetch_related("owner")
    EmailMailboxEntry(read_thread)._refresh_content_and_mark_unread(entry)
    assert MailboxLabel.UNREAD not in entry.labels

    # Test unread thread
    unread_thread = await create_email_thread(
        creator_id=owner.id,
        organization_id=organization.id,
        title="Unread Thread",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
    )
    await unread_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=unread_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],  # Start as read
    )
    await entry.fetch_related("owner")
    EmailMailboxEntry(unread_thread)._refresh_content_and_mark_unread(entry)
    assert MailboxLabel.UNREAD in entry.labels

    #
    # Test collaborator label syncing
    #
    #

    # Test new shared entry gets inbox and unread labels
    shared_thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Shared Thread", labels=[EmailLabel.SENT]
    )
    await shared_thread.fetch_related(
        "messages__attachments",
        "comments",
        "workspace__events",
        "workspace__attachments",
    )

    # Create new entry for collaborator
    collab_entry = MailboxEntry(
        owner_id=collaborator.id,
        organization_id=organization.id,
        resource_gid=shared_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],
    )
    await collab_entry.fetch_related("owner")
    EmailMailboxEntry(shared_thread)._refresh_content_and_mark_unread(collab_entry)

    # New shared entries should get inbox and unread
    assert MailboxLabel.INBOX in collab_entry.labels
    assert MailboxLabel.UNREAD in collab_entry.labels
    assert EmailMailboxLabel.SENT not in collab_entry.labels  # Collaborators don't inherit SENT labels


@pytest.mark.asyncio
async def test_sync_from_activity_detection():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Thread with New Activity"
    )
    await email_thread.fetch_related(
        "messages__attachments", "comments", "workspace__events", "workspace__attachments"
    )

    # Create existing entry that's been read and archived
    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],  # Archived and read
        last_activity_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),  # Older timestamp
    )
    await owner_entry.save()
    await owner_entry.fetch_related("owner")

    # Simulate new activity by creating a new message
    await create_email_message(
        user_id=owner.id,
        organization_id=owner.organization_id,
        external_thread_id=email_thread.external_thread_id,
        subject="New activity message",
        received_at=datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC),
    )
    await email_thread.update_metadata_from_messages()
    await email_thread.fetch_related(
        "messages__attachments", "comments", "workspace__events", "workspace__attachments"
    )
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(owner_entry)

    # Owner should get unread due to new activity
    assert MailboxLabel.UNREAD in owner_entry.labels
    assert MailboxLabel.INBOX in owner_entry.labels

    # Test collaborator gets forced unread and inbox on new activity
    collaborator_entry = MailboxEntry(
        owner_id=collaborator.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",  # Required field
        preview="Initial Preview",  # Required field
        labels=[],  # Archived and read
        last_activity_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),  # Older timestamp
    )
    await collaborator_entry.save()
    await collaborator_entry.fetch_related("owner")

    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(collaborator_entry)
    assert MailboxLabel.UNREAD in collaborator_entry.labels
    assert MailboxLabel.INBOX in collaborator_entry.labels


@pytest.mark.asyncio
async def test_sync_from_activity_detection_owner_message_no_activity():
    """Test that owner sending a message themselves does NOT trigger has_new_activity_from_others."""
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Thread with Owner Activity"
    )
    await email_thread.fetch_related(
        "messages__attachments", "comments", "workspace__events", "workspace__attachments"
    )

    # Create existing entry that's been read and archived
    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],  # Archived and read
        last_activity_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),  # Older timestamp
    )
    await owner_entry.save()
    await owner_entry.fetch_related("owner")

    # Simulate owner sending a message themselves (sender = owner's email)
    # Don't automatically label as INBOX since this is the owner's own activity
    await create_email_message(
        user_id=owner.id,
        organization_id=owner.organization_id,
        external_thread_id=email_thread.external_thread_id,
        subject="Message from owner themselves",
        sender=f"{owner.name} <{owner.email}>",  # Owner is the sender
        received_at=datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC),
        labels=[],  # No automatic INBOX label for owner's own activity
    )
    await email_thread.update_metadata_from_messages()
    await email_thread.fetch_related(
        "messages__attachments", "comments", "workspace__events", "workspace__attachments"
    )
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(owner_entry)

    # Owner should NOT get unread/inbox due to their own activity
    assert MailboxLabel.UNREAD not in owner_entry.labels
    assert MailboxLabel.INBOX not in owner_entry.labels


@pytest.mark.asyncio
async def test_sync_from_activity_detection_owner_comment_no_activity():
    """Test that owner adding a comment themselves does NOT trigger has_new_activity_from_others."""
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Thread with Owner Comment", labels=[]
    )

    # Create existing entry that's been read and archived
    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],  # Archived and read
        last_activity_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),  # Older timestamp
    )
    await owner_entry.save()
    await owner_entry.fetch_related("owner")

    # Owner adds a comment themselves
    comment = EmailThreadComment(
        email_thread_id=email_thread.id, user_id=owner.id, content="Comment from owner themselves"
    )
    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=owner.id
    ) as recording:
        await comment.save(recording.using_db)

    await email_thread.fetch_related(
        "messages__attachments", "comments", "workspace__events", "workspace__attachments"
    )
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(owner_entry)

    # Owner should NOT get unread/inbox due to their own comment
    assert MailboxLabel.UNREAD not in owner_entry.labels
    assert MailboxLabel.INBOX not in owner_entry.labels


@pytest.mark.asyncio
async def test_sync_from_activity_detection_collaborator_comment_triggers_activity():
    """Test that a collaborator adding a comment DOES trigger has_new_activity_from_others."""
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Thread with Collaborator Comment"
    )

    # Add collaborator
    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=collaborator.id)

    # Create existing entry that's been read and archived
    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],  # Archived and read
        last_activity_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),  # Older timestamp
    )
    await owner_entry.save()
    await owner_entry.fetch_related("owner")

    # Collaborator adds a comment
    comment = EmailThreadComment(
        email_thread_id=email_thread.id, user_id=collaborator.id, content="Comment from collaborator"
    )
    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=collaborator.id
    ) as recording:
        await comment.save(recording.using_db)

    await email_thread.fetch_related(
        "messages__attachments", "comments", "workspace__events", "workspace__attachments"
    )
    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(owner_entry)

    # Owner should get unread/inbox due to collaborator's comment
    assert MailboxLabel.UNREAD in owner_entry.labels
    assert MailboxLabel.INBOX in owner_entry.labels


# ---------------------------------------------------------------------------
# An archived thread must never reappear in the Convictional inbox. `_sync_inbox_state`
# adds INBOX based on activity, but a thread that Gmail has archived (all its inbound
# RECEIVED mail is out of the inbox) must stay out — even when there is "new activity
# from others". The tricky constraint: an ALL-OUTGOING thread (assignee sent + creator
# replied, no inbound) also reads as archived by label-union math, yet SHOULD stay in
# the inbox. The distinguishing signal is whether the thread has inbound RECEIVED mail
# that Gmail has archived; all-outgoing threads have no inbound mail at all.
# ---------------------------------------------------------------------------


async def _build_archived_inbound_thread(owner, organization):
    """An archived thread with an existing (non-new) owner entry and one inbound,
    not-in-inbox RECEIVED message — the shape of a Gmail-archived conversation."""
    thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Archived Inbound", labels=[]
    )
    await create_email_message(
        user_id=owner.id,
        organization_id=organization.id,
        external_thread_id=thread.external_thread_id,
        subject="Archived Inbound",
        sender="someone@external.com",
        received_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
        labels=[],  # inbound, archived in Gmail (no INBOX)
    )
    await thread.update_metadata_from_messages()
    return thread


@pytest.mark.asyncio
async def test_archived_inbound_thread_with_newer_inbound_stays_out_of_owner_inbox():
    """O1b: a newer inbound message that is ALSO archived in Gmail must not re-inbox the owner."""
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    thread = await _build_archived_inbound_thread(owner, organization)

    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=thread.global_id,
        title="Archived Inbound",
        preview="Archived Inbound",
        labels=[],  # archived
        last_activity_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
    )
    await owner_entry.save()
    await owner_entry.fetch_related("owner")

    # A newer inbound reply from someone else lands, still archived in Gmail (no INBOX).
    await create_email_message(
        user_id=owner.id,
        organization_id=organization.id,
        external_thread_id=thread.external_thread_id,
        subject="Re: Archived Inbound",
        sender="someone@external.com",
        received_at=datetime(2024, 1, 2, 9, 0, 0, tzinfo=UTC),
        labels=[],
    )
    await thread.update_metadata_from_messages()
    await thread.fetch_related("messages__attachments", "comments", "workspace__events", "workspace__attachments")
    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(owner_entry)

    # has_new_activity is True (newer message from others), but Gmail still has the thread
    # archived, so the entry must NOT be pulled into the inbox.
    assert MailboxLabel.INBOX not in owner_entry.labels


@pytest.mark.asyncio
async def test_archived_inbound_thread_stays_out_of_new_collaborator_inbox():
    """A new collaborator (is_shared=True) entry on an archived thread must stay out of the inbox."""
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)
    thread = await _build_archived_inbound_thread(owner, organization)
    await create_collaborator(workspace_id=thread.workspace_id, user_id=collaborator.id)

    collaborator_entry = MailboxEntry(
        owner_id=collaborator.id,
        organization_id=organization.id,
        resource_gid=thread.global_id,
        title="Archived Inbound",
        preview="Archived Inbound",
        labels=[],
    )
    await collaborator_entry.fetch_related("owner")

    await thread.fetch_related("messages__attachments", "comments", "workspace__events", "workspace__attachments")
    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(collaborator_entry)

    # The is_shared branch adds INBOX on a new entry, but the thread is archived in Gmail.
    assert collaborator_entry.is_shared is True
    assert MailboxLabel.INBOX not in collaborator_entry.labels


@pytest.mark.asyncio
async def test_all_outgoing_thread_stays_in_owner_inbox():
    """An all-outgoing thread (assignee sent + creator replied, no inbound) reads as archived by
    label-union math, but has no inbound mail — it must stay in the owner's inbox."""
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    assignee = await create_user(organization_id=organization.id)
    thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="All Outgoing", labels=[]
    )

    # Assignee sends (SENT, no INBOX) and the creator replies (SENT, no INBOX). No inbound mail.
    await create_email_message(
        user_id=owner.id,
        organization_id=organization.id,
        external_thread_id=thread.external_thread_id,
        message_type=EmailMessageType.SENT,
        subject="All Outgoing",
        sender=f"{assignee.name} <{assignee.email}>",
        received_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
        labels=[EmailLabel.SENT],
    )
    await thread.update_metadata_from_messages()

    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=thread.global_id,
        title="All Outgoing",
        preview="All Outgoing",
        labels=[],
        last_activity_at=datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC),
    )
    await owner_entry.save()
    await owner_entry.fetch_related("owner")

    # The assignee (from the owner's perspective, "other") sends a newer message.
    await create_email_message(
        user_id=owner.id,
        organization_id=organization.id,
        external_thread_id=thread.external_thread_id,
        message_type=EmailMessageType.SENT,
        subject="All Outgoing",
        sender=f"{assignee.name} <{assignee.email}>",
        received_at=datetime(2024, 1, 2, 9, 0, 0, tzinfo=UTC),
        labels=[EmailLabel.SENT],
    )
    await thread.update_metadata_from_messages()
    await thread.fetch_related("messages__attachments", "comments", "workspace__events", "workspace__attachments")
    assert not thread.is_inbox  # label-union over outgoing-only messages reads as archived
    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(owner_entry)

    # No inbound mail to archive, so the all-outgoing thread must surface in the inbox.
    assert MailboxLabel.INBOX in owner_entry.labels


@pytest.mark.asyncio
async def test_new_inbound_with_inbox_label_reopens_archived_thread():
    """A genuinely new inbound message carrying INBOX re-opens an archived/closed thread."""
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    thread = await _build_archived_inbound_thread(owner, organization)

    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=thread.global_id,
        title="Archived Inbound",
        preview="Archived Inbound",
        labels=[],  # archived
        last_activity_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
    )
    await owner_entry.save()
    await owner_entry.fetch_related("owner")

    # New inbound reply that Gmail DID put in the inbox.
    await create_email_message(
        user_id=owner.id,
        organization_id=organization.id,
        external_thread_id=thread.external_thread_id,
        subject="Re: Archived Inbound",
        sender="someone@external.com",
        received_at=datetime(2024, 1, 2, 9, 0, 0, tzinfo=UTC),
        labels=[EmailLabel.INBOX],
    )
    await thread.update_metadata_from_messages()
    await thread.fetch_related("messages__attachments", "comments", "workspace__events", "workspace__attachments")
    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(owner_entry)

    # Inbound mail is back in the Gmail inbox, so the thread re-opens in Convictional.
    assert MailboxLabel.INBOX in owner_entry.labels


@pytest.mark.asyncio
async def test_self_sent_inbox_message_stays_in_owner_inbox():
    """A self-sent Gmail message (SENT + INBOX, message_type SENT) must land in the inbox.

    `_received_mail_is_archived` must classify self-sent mail as outgoing (SENT, not RECEIVED)
    so it is never counted as archived inbound mail and never suppressed."""
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Self Sent", labels=[]
    )

    await create_email_message(
        user_id=owner.id,
        organization_id=organization.id,
        external_thread_id=thread.external_thread_id,
        message_type=EmailMessageType.SENT,
        subject="Self Sent",
        sender=f"{owner.name} <{owner.email}>",
        received_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
        labels=[EmailLabel.SENT, EmailLabel.INBOX],
    )
    await thread.update_metadata_from_messages()

    owner_entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=thread.global_id,
        title="Self Sent",
        preview="Self Sent",
        labels=[],
    )
    await owner_entry.fetch_related("owner")

    await thread.fetch_related("messages__attachments", "comments", "workspace__events", "workspace__attachments")
    assert thread.is_inbox  # the self-sent message carries INBOX
    EmailMailboxEntry(thread)._refresh_content_and_mark_unread(owner_entry)

    assert MailboxLabel.INBOX in owner_entry.labels


@pytest.mark.asyncio
async def test_mailbox_entry_counter_fields():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    # Create email thread with multiple messages
    first_message = await create_email_message(
        user_id=owner.id,
        organization_id=organization.id,
        external_thread_id="counter_test",
        subject="Test Message 1",
        sender="sender1@example.com",
    )
    second_message = await create_email_message(
        user_id=owner.id,
        organization_id=organization.id,
        external_thread_id="counter_test",
        subject="Test Message 2",
        sender="sender2@example.com",
    )

    thread = await EmailThread.get(id=first_message.thread_id)

    # Create file references for attachments
    file1 = await FileReference.create(
        key="test/file1.pdf", filename="file1.pdf", content_type="application/pdf", byte_size=1024, checksum="abc123"
    )
    file2 = await FileReference.create(
        key="test/file2.png", filename="file2.png", content_type="image/png", byte_size=2048, checksum="def456"
    )
    file3 = await FileReference.create(
        key="test/workspace_file.doc",
        filename="workspace_file.doc",
        content_type="application/msword",
        byte_size=3072,
        checksum="ghi789",
    )

    # Create email attachments
    await EmailAttachment.create(
        email_message_id=first_message.id,
        file_id=file1.id,
        thread_id=thread.id,
    )
    await EmailAttachment.create(
        email_message_id=second_message.id,
        file_id=file2.id,
        thread_id=thread.id,
    )

    # Add collaborator and create comments
    await create_collaborator(workspace_id=thread.workspace_id, user_id=collaborator.id)

    comment1 = EmailThreadComment(email_thread_id=thread.id, user_id=owner.id, content="First comment")
    await thread.fetch_related("workspace")
    async with thread.workspace.record(EventAction.COMMENTED, recordable=comment1, creator_id=owner.id) as recording:
        await comment1.save(recording.using_db)

    comment2 = EmailThreadComment(email_thread_id=thread.id, user_id=collaborator.id, content="Second comment")
    async with thread.workspace.record(
        EventAction.COMMENTED, recordable=comment2, creator_id=collaborator.id
    ) as recording:
        await comment2.save(recording.using_db)

    # Create workspace attachment linked to comment
    await Attachment.create(
        title="Workspace Document",
        user_id=owner.id,
        file_id=file3.id,
        workspace_id=thread.workspace_id,
        comment_gid=comment1.global_id,
    )

    # Sync mailbox entry and test counter fields
    await thread.fetch_related(
        "workspace__collaborators__user",
        "workspace__events",
        "comments",
        "workspace__attachments",
        "messages__attachments",
    )

    mailbox_sync = await EmailMailboxEntry(thread).refresh_row_and_mark_unread(owner)
    assert mailbox_sync is not None
    mailbox_entry = await MailboxEntry.get(id=mailbox_sync.entry_id)
    assert mailbox_entry.workspace_attachment_count == 1


@pytest.mark.asyncio
async def test_mailbox_sync_archived_thread_becomes_unread_on_new_message():
    owner = await create_user(email="owner@example.com")

    old_message = await create_email_message(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        sender="sender@example.com",
        labels=[],
        received_at=datetime(2026, 3, 20, tzinfo=UTC),
    )

    thread = await EmailThread.get(id=old_message.thread_id)
    await Mailbox.sync(thread)

    entry = await MailboxEntry.filter(resource_gid=str(thread.global_id), owner_id=owner.id).first()
    assert entry is not None

    await entry.archive()

    # sender differs from owner email so these messages count as "from others" in _sync_labels
    await create_email_message(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        external_thread_id=thread.external_thread_id,
        sender="sender@example.com",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        received_at=datetime(2026, 3, 26, tzinfo=UTC),
    )

    thread = await EmailThread.get(id=thread.id)
    await Mailbox.sync(thread)

    entry = await MailboxEntry.get(id=entry.id)
    assert EmailLabel.UNREAD in entry.labels, "Entry should be unread after new message from others"
    assert EmailLabel.INBOX in entry.labels, "Entry should be back in inbox"


@pytest.mark.asyncio
async def test_mailbox_sync_double_sync_preserves_unread_state():
    owner = await create_user(email="owner@example.com")

    old_message = await create_email_message(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        sender="sender@example.com",
        labels=[],
        received_at=datetime(2026, 3, 20, tzinfo=UTC),
    )

    thread = await EmailThread.get(id=old_message.thread_id)
    await Mailbox.sync(thread)

    entry = await MailboxEntry.filter(resource_gid=str(thread.global_id), owner_id=owner.id).first()
    assert entry is not None

    await entry.archive()

    # sender differs from owner email so these messages count as "from others" in _sync_labels
    await create_email_message(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        external_thread_id=thread.external_thread_id,
        sender="sender@example.com",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        received_at=datetime(2026, 3, 26, tzinfo=UTC),
    )

    thread = await EmailThread.get(id=thread.id)
    await Mailbox.sync(thread)

    entry = await MailboxEntry.get(id=entry.id)
    assert EmailLabel.UNREAD in entry.labels, "Entry should be unread after first sync"
    assert EmailLabel.INBOX in entry.labels, "Entry should be in inbox after first sync"

    # Simulate GmailMessageStateProcessor stripping UNREAD from the thread object
    # before the second Mailbox.sync() call (as happens when labels are re-fetched
    # from Gmail and update_metadata_from_messages() runs with a stale message state).
    # Mailbox.sync() calls fetch_related() which refreshes related objects but does NOT
    # reload the thread's own scalar fields (e.g. labels), so the stale value persists.
    thread = await EmailThread.get(id=thread.id)
    thread.labels = [EmailLabel.INBOX]  # UNREAD stripped from thread
    await Mailbox.sync(thread)

    entry = await MailboxEntry.get(id=entry.id)
    assert EmailLabel.UNREAD in entry.labels, "Entry should still be unread after second sync with stale thread"
    assert EmailLabel.INBOX in entry.labels, "Entry should still be in inbox after second sync"


@pytest.mark.asyncio
async def test_mailbox_sync_double_sync_preserves_archived_state():
    owner = await create_user(email="owner@example.com")

    old_message = await create_email_message(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        sender="sender@example.com",
        labels=[],
        received_at=datetime(2026, 3, 20, tzinfo=UTC),
    )

    thread = await EmailThread.get(id=old_message.thread_id)
    await Mailbox.sync(thread)

    entry = await MailboxEntry.filter(resource_gid=str(thread.global_id), owner_id=owner.id).first()
    assert entry is not None

    await entry.archive()

    # Add a new message from someone other than the owner to trigger new activity from others
    await create_email_message(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        external_thread_id=thread.external_thread_id,
        sender="sender@example.com",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        received_at=datetime(2026, 3, 26, tzinfo=UTC),
    )

    thread = await EmailThread.get(id=thread.id)
    await Mailbox.sync(thread)

    entry = await MailboxEntry.get(id=entry.id)
    assert MailboxLabel.INBOX in entry.labels, "Entry should be in inbox after new activity"

    # Archive the entry again
    await entry.archive()

    entry = await MailboxEntry.get(id=entry.id)
    assert MailboxLabel.INBOX not in entry.labels, "Entry should be archived after second archive"

    # Simulate stale thread-level state: update_metadata_from_messages() rebuilds
    # thread.labels from message-level labels which still have INBOX, making
    # email_thread.is_inbox == True even though the user archived the entry.
    thread = await EmailThread.get(id=thread.id)
    thread.labels = [EmailLabel.INBOX]
    await Mailbox.sync(thread)

    entry = await MailboxEntry.get(id=entry.id)
    assert MailboxLabel.INBOX not in entry.labels, "Entry should remain archived after sync with stale thread labels"


@pytest.mark.asyncio
async def test_email_refresh_content_does_not_unsnooze():
    # Snooze-leak fix (email's own _refresh_content): the content-only path — used by
    # mark_as_read/unread — must not clear a snooze even when there's new activity from
    # others. Only the surfacing path (_refresh_content_and_mark_unread) does. Under the
    # pre-split code the unsnooze lived in the shared content apply, so a refresh cleared it.
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Snoozed thread"
    )
    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=collaborator.id)

    snoozed_until = datetime(2030, 1, 1, tzinfo=UTC)
    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],
        last_activity_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
        snoozed_until=snoozed_until,
    )
    await entry.save()
    await entry.fetch_related("owner")

    # New activity from others — would set has_new_activity=True (the trigger the old
    # shared-apply unsnooze keyed on).
    comment = EmailThreadComment(email_thread_id=email_thread.id, user_id=collaborator.id, content="new activity")
    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=collaborator.id
    ) as recording:
        await comment.save(recording.using_db)
    await email_thread.fetch_related(
        "messages__attachments", "comments", "workspace__events", "workspace__attachments"
    )

    EmailMailboxEntry(email_thread)._refresh_content(entry)

    assert entry.snoozed_until == snoozed_until  # content-only refresh leaves the snooze intact


@pytest.mark.asyncio
async def test_email_recovery_wakes_snoozed_entry():
    # Positive twin of test_email_refresh_content_does_not_unsnooze: the surfacing path
    # (_refresh_content_and_mark_unread, used when a lagging/recovered Gmail message is
    # processed) MUST wake a snoozed entry on new activity from others — re-inbox it and
    # clear the snooze. This is the intended snooze-exit contract; it does not collide with
    # the _received_mail_is_archived guard because a snoozed thread's Gmail mail keeps INBOX.
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(
        creator_id=owner.id, organization_id=organization.id, title="Snoozed thread"
    )
    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=collaborator.id)

    snoozed_until = datetime(2030, 1, 1, tzinfo=UTC)
    entry = MailboxEntry(
        owner_id=owner.id,
        organization_id=organization.id,
        resource_gid=email_thread.global_id,
        title="Initial Title",
        preview="Initial Preview",
        labels=[],
        last_activity_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
        snoozed_until=snoozed_until,
    )
    await entry.save()
    await entry.fetch_related("owner")

    # New activity from others — sets has_new_activity=True, the snooze-cancelling trigger.
    comment = EmailThreadComment(email_thread_id=email_thread.id, user_id=collaborator.id, content="new activity")
    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=collaborator.id
    ) as recording:
        await comment.save(recording.using_db)
    await email_thread.fetch_related(
        "messages__attachments", "comments", "workspace__events", "workspace__attachments"
    )

    EmailMailboxEntry(email_thread)._refresh_content_and_mark_unread(entry)

    assert entry.snoozed_until is None  # surfacing path clears the snooze on new activity
    assert MailboxLabel.INBOX in entry.labels  # and re-inboxes the thread


@pytest.mark.asyncio
async def test_direct_recipient_surfaces_past_gmail_archive_gate():
    # An @mention or assignment on an email thread whose inbound mail Gmail has archived must
    # still reach the target's inbox. A direct recipient is force-surfaced past the Gmail-archive
    # gate; a collaborator merely reached by force-include stays gated, so targeting one person
    # never resurfaces the archived thread for everyone.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    target = await create_user(organization_id=organization.id)
    bystander = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(creator_id=sender.id, organization_id=organization.id, labels=[])

    # Inbound mail with no INBOX label → the thread reads as Gmail-archived.
    archived_message = EmailMessage(
        external_message_id="archived_msg_8711",
        external_thread_id=email_thread.external_thread_id,
        subject="Archived",
        sender="outside@example.com",
        to=["team@example.com"],
        body_plain="hi",
        user_id=sender.id,
        organization_id=organization.id,
        message_type=EmailMessageType.RECEIVED,
        thread_id=email_thread.id,
        labels=[],
    )
    await archived_message.save()
    await email_thread.update_metadata_from_messages()

    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=target.id)
    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=bystander.id)

    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(EventAction.COMMENTED, creator_id=sender.id) as recording:
        event = recording.event

    await Mailbox.sync(email_thread, event=event, direct_recipients=[target])

    target_entry = await MailboxEntry.get(resource_gid=email_thread.global_id, owner_id=target.id)
    assert MailboxLabel.INBOX in target_entry.labels
    assert MailboxLabel.UNREAD in target_entry.labels

    bystander_entry = await MailboxEntry.get(resource_gid=email_thread.global_id, owner_id=bystander.id)
    assert MailboxLabel.INBOX not in bystander_entry.labels


@pytest.mark.asyncio
async def test_sync_mailbox_job_folds_assignee_into_direct_recipients():
    # The assignee of an ASSIGNED event is folded into direct recipients from the event's
    # point-in-time details, so assignment surfaces like an @mention regardless of the
    # assignee's subscription level or the thread's Gmail archive state.
    organization = await create_organization()
    actor = await create_user(organization_id=organization.id)
    assignee = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(creator_id=actor.id, organization_id=organization.id)

    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(EventAction.ASSIGNED, creator_id=actor.id) as recording:
        recording.event.details = {"assignee": {"id": str(assignee.id)}}

    recipients = await SubscriberResolver(workspace=email_thread.workspace).direct_recipients_for(recording.event)
    assert {u.id for u in recipients} == {assignee.id}


@pytest.mark.asyncio
async def test_sync_mailbox_job_folds_self_assignment_into_direct_recipients():
    # A self-assignment is a direct ask to yourself, so the self-assigner is a direct recipient
    # too — InboxUpdate.for_event then force-surfaces their row (mark unread), exactly like a
    # self-mention.
    organization = await create_organization()
    actor = await create_user(organization_id=organization.id)
    email_thread = await create_email_thread(creator_id=actor.id, organization_id=organization.id)

    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(EventAction.ASSIGNED, creator_id=actor.id) as recording:
        recording.event.details = {"assignee": {"id": str(actor.id)}}

    recipients = await SubscriberResolver(workspace=email_thread.workspace).direct_recipients_for(recording.event)
    assert {u.id for u in recipients} == {actor.id}
