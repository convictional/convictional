from datetime import UTC, date, datetime, timedelta

import pytest
from freezegun import freeze_time

from app.jobs.content import (
    ContentIndexingJob,
    IndexChatHistoryJob,
    IndexChatJob,
    IndexEmailContactJob,
    IndexEmailThreadJob,
    UpdateChatContentAccessJob,
    invalidate_chat_history_indexing,
)
from app.models.collaboration.content import Content, ContentIndexer, ContentLookup, IndexingID
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import Mailbox
from app.models.collaboration.workspace import Collaborator
from app.models.workspaces.chat import Chat
from app.models.workspaces.documents import DocumentComment
from app.models.workspaces.email.thread import EmailAttachment, EmailThread
from config import settings
from config.enums import AccessAction, ContentType, EventAction, GoalStatus, ReactionType, Sharing
from infra.storage import FileReference
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_collaborator,
    create_content,
    create_document,
    create_email_alias,
    create_email_contact,
    create_email_message,
    create_email_thread_comment,
    create_event,
    create_goal,
    create_goal_comment,
    create_group,
    create_meeting,
    create_organization,
    create_post,
    create_post_comment,
    create_subgoal,
    create_user,
)

#
# Email contact indexing
#
#


@pytest.mark.asyncio
async def test_index_email_contact_creates_content():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    email_contact = await create_email_contact(
        email="external@example.com", name="External Contact", organization_id=organization.id, user_id=user.id
    )
    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_contact.global_id))
    await IndexEmailContactJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.content_type == ContentType.EMAIL_CONTACT
    assert "External Contact" in content.index_content
    assert "external@example.com" in content.index_content
    assert content.allowed_user_ids == [str(user.id)]

    contact_no_name = await create_email_contact(
        email="noname@example.com", name=None, organization_id=organization.id, user_id=user.id
    )
    no_name_indexing_id = IndexingID(organization_id=organization.id, source_id=str(contact_no_name.global_id))
    await IndexEmailContactJob(indexing_id=no_name_indexing_id).perform()

    content_no_name = await Content.get_by_indexing_id(no_name_indexing_id).first()
    assert content_no_name is not None
    assert "noname@example.com" in content_no_name.title


@pytest.mark.asyncio
async def test_index_email_contact_skips_content_for_existing_user_emails_and_aliases():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, email="john@example.com")
    await create_email_alias(address="alias@example.com", user_id=user.id)

    contact_matching_user = await create_email_contact(
        email="john@example.com", name="John Duplicate", organization_id=organization.id, user_id=user.id
    )
    user_indexing_id = IndexingID(organization_id=organization.id, source_id=str(contact_matching_user.global_id))
    await IndexEmailContactJob(indexing_id=user_indexing_id).perform()

    user_content = await Content.get_by_indexing_id(user_indexing_id).first()
    assert user_content is None

    contact_matching_alias = await create_email_contact(
        email="alias@example.com", name="Alias Contact", organization_id=organization.id, user_id=user.id
    )
    alias_indexing_id = IndexingID(organization_id=organization.id, source_id=str(contact_matching_alias.global_id))
    await IndexEmailContactJob(indexing_id=alias_indexing_id).perform()

    alias_content = await Content.get_by_indexing_id(alias_indexing_id).first()
    assert alias_content is None


@pytest.mark.asyncio
async def test_index_user_cleans_up_email_contacts_for_user_and_aliases():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, email="john@example.com")

    await create_email_alias(address="john.doe@example.com", user_id=user.id)

    email_contact_1 = await create_email_contact(
        email="john@example.com", name="John 1", organization_id=organization.id, user_id=user.id
    )
    email_contact_2 = await create_email_contact(
        email="john.doe@example.com", name="John 2", organization_id=organization.id, user_id=user.id
    )

    contact_1_indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_contact_1.global_id))
    contact_2_indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_contact_2.global_id))

    await ContentIndexingJob.from_model(organization.id, user).perform()

    content_1 = await Content.get_by_indexing_id(contact_1_indexing_id).first()
    content_2 = await Content.get_by_indexing_id(contact_2_indexing_id).first()

    assert content_1 is None
    assert content_2 is None


@pytest.mark.asyncio
async def test_multiple_email_contacts_same_name_different_emails():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    contact1 = await create_email_contact(
        email="john1@example.com", name="John Smith", organization_id=organization.id, user_id=user.id
    )
    contact2 = await create_email_contact(
        email="john2@example.com", name="John Smith", organization_id=organization.id, user_id=user.id
    )

    indexing_id_1 = IndexingID(organization_id=organization.id, source_id=str(contact1.global_id))
    indexing_id_2 = IndexingID(organization_id=organization.id, source_id=str(contact2.global_id))

    await IndexEmailContactJob(indexing_id=indexing_id_1).perform()
    await IndexEmailContactJob(indexing_id=indexing_id_2).perform()

    content1 = await Content.get_by_indexing_id(indexing_id_1).first()
    content2 = await Content.get_by_indexing_id(indexing_id_2).first()

    assert content1 is not None
    assert content2 is not None
    assert content1.id != content2.id


@pytest.mark.asyncio
async def test_index_email_thread_proper_updated_at():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    one_month_ago = datetime.now() - timedelta(days=30)
    with freeze_time(one_month_ago):
        email_message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="indexing_test",
            subject="Test Message",
            sender="sender@example.com",
        )
    email_thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(email_thread)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.updated_at == email_thread.updated_at


@pytest.mark.asyncio
async def test_index_post_updated_at_reflects_workspace_activity():
    # SERP recency ranks on Content.updated_at, but activity (a comment or decision) records a
    # workspace event without re-saving the post, so post.updated_at stays stale. The indexed
    # row must track workspace.last_event_at so a freshly active post keeps its recency boost.
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    one_month_ago = datetime.now(UTC) - timedelta(days=30)
    with freeze_time(one_month_ago):
        post = await create_post(organization_id=organization.id, creator_id=user.id)
    await post.fetch_related("workspace")

    recent_event = await create_event(post.workspace, creator_id=user.id, action=EventAction.POST_COMMENTED)

    await ContentIndexingJob.from_model(organization.id, post).perform()

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(post.global_id))
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert recent_event.created_at > post.updated_at
    assert content.updated_at == recent_event.created_at


@pytest.mark.asyncio
async def test_index_chat_updated_at_reflects_message_and_event_activity():
    # Chat recency folds the last message on top of the base event-log signal: a new message
    # advances recency, and a later comment/decision (a workspace event, no new message) does too.
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    with freeze_time(thirty_days_ago):
        chat = await create_chat(organization_id=organization.id, creator_id=user.id)

    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    with freeze_time(ten_days_ago):
        await create_chat_message(chat_id=chat.id, user_id=user.id)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(chat.global_id))
    await ContentIndexingJob.from_model(organization.id, chat).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    chat = await Chat.get(id=chat.id).prefetch_related("workspace")
    assert content is not None
    assert content.updated_at == chat.last_message_at

    one_day_ago = datetime.now(UTC) - timedelta(days=1)
    with freeze_time(one_day_ago):
        event = await create_event(chat.workspace, creator_id=user.id, action=EventAction.DECIDED)

    await ContentIndexingJob.from_model(organization.id, chat).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.updated_at == event.created_at


@pytest.mark.asyncio
async def test_index_email_thread_updated_at_reflects_message_and_event_activity():
    # Email thread recency folds the last message on top of the base event-log signal: inbound
    # mail advances recency, and a later comment/decision (a workspace event) does too.
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    with freeze_time(thirty_days_ago):
        email_message = await create_email_message(
            user_id=user.id,
            organization_id=organization.id,
            external_thread_id="activity_test",
            subject="Test",
            sender="sender@example.com",
        )
    email_thread = await EmailThread.get(id=email_message.thread_id).prefetch_related("messages", "workspace")

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await ContentIndexingJob.from_model(organization.id, email_thread).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.updated_at == email_thread.last_message_at

    one_day_ago = datetime.now(UTC) - timedelta(days=1)
    with freeze_time(one_day_ago):
        event = await create_event(email_thread.workspace, creator_id=user.id, action=EventAction.COMMENTED)

    await ContentIndexingJob.from_model(organization.id, email_thread).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.updated_at == event.created_at


@pytest.mark.asyncio
async def test_index_email_thread_resolves_participants_to_global_ids():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, email="user@example.com")
    await create_user(organization_id=organization.id, email="other@example.com")

    # Create an email contact for a participant who is not a user
    await create_email_contact(
        organization_id=organization.id, user_id=user.id, email="external@example.com", name="External Contact"
    )

    # Create an email message with multiple participants
    email_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="participant_test",
        subject="Test Message with Participants",
        sender="user@example.com",
        to=["other@example.com", "external@example.com", "unknown@example.com"],
        cc=["user@example.com"],
    )

    email_thread = await EmailThread.get(id=email_message.thread_id)
    await email_thread.fetch_related("messages", "creator", "workspace__collaborators", "comments__user")


@pytest.mark.asyncio
async def test_index_email_thread_deduplicates_authors():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, email="user@example.com", display_name="User Name")

    # Create multiple messages with the same email in different capitalizations
    first_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="dedup_test",
        subject="Test Thread",
        sender="user@example.com",
        to=["other@example.com"],
    )
    await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="dedup_test",
        subject="Re: Test Thread",
        sender="USER@EXAMPLE.COM",
        to=["other@example.com"],
        from_address="other@example.com",
    )
    await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="dedup_test",
        subject="Re: Test Thread",
        sender="User.Name <user@EXAMPLE.com>",
        to=["other@example.com"],
    )

    email_thread = await EmailThread.get(id=first_message.thread_id)
    await Mailbox.sync(email_thread)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None

    # Verify that the author field doesn't contain duplicates of the same email
    author_list = content.author.split(", ")
    # Should have exactly 2 unique participants (user@example.com and other@example.com)
    assert len(author_list) == 2
    # Verify no case-insensitive duplicates
    author_emails_lower = [author.lower() for author in author_list]
    assert len(author_emails_lower) == len(set(author_emails_lower))


@pytest.mark.asyncio
async def test_index_email_thread_puts_research_email_first():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, email="user@example.com", display_name="User Name")

    email_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="research_first_test",
        subject="Research Thread",
        sender="user@example.com",
        to=[settings.research_email_from],
    )

    email_thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(email_thread)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None

    author_list = content.author.split(", ")
    assert settings.research_email_from in author_list[0]


@pytest.mark.asyncio
async def test_index_email_thread_always_indexes_with_ai_exclusion_flag():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    email_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="excluded_test",
        subject="Excluded Thread",
        sender="sender@example.com",
    )
    email_thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(email_thread)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))

    # Indexing always creates Content regardless of exclusion state
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.is_ai_excluded is False


@pytest.mark.asyncio
async def test_index_email_thread_strips_reply_quotes():
    """Uses real Gmail/Convictional reply content from email seeds (19b08486f3a2231f.json)."""
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    email_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="quote_stripping_test",
        subject="Test gmail quoted reply placement",
        sender="marcus@example.com",
        body_plain="This is the initial email content.\r\n",
    )
    email_thread = await EmailThread.get(id=email_message.thread_id)

    await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="quote_stripping_test",
        subject="Re: Test gmail quoted reply placement",
        sender="marcus@example.com",
        body_plain=(
            "And this is the reply inside Gmail.\r\n\r\n"
            "On Wed, Dec 10, 2025 at 7:42\u202fAM Marcus Larkin <marcus@example.com> wrote:\r\n\r\n"
            "> This is the initial email content.\r\n>\r\n"
        ),
    )

    await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="quote_stripping_test",
        subject="Re: Test gmail quoted reply placement",
        sender="marcus@example.com",
        body_plain=(
            "This is the reply inside Convictional.\n\n"
            "On December 10, 2025 at 07:42 AM, Marcus Larkin wrote:\n"
            "...\n"
            "And this is the reply inside Gmail.\n\n"
            "On Wed, Dec 10, 2025 at 7:42\u202fAM Marcus Larkin "
            "<marcus@example.com (mailto:marcus@example.com)> wrote:\n"
            "This is the initial email content."
        ),
    )
    await email_thread.refresh_from_db()
    await Mailbox.sync(email_thread)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None

    # Gmail reply (message 2): quote is stripped, only the reply text remains.
    # Convictional reply (message 3): attribution line starts on its own line,
    # so the parser correctly identifies and strips the quoted content.
    # "initial email content" only appears in message 1 (the original).
    assert content.index_content.count("This is the initial email content.") == 1
    assert content.index_content.count("And this is the reply inside Gmail.") == 1
    assert "This is the reply inside Convictional." in content.index_content


@pytest.mark.asyncio
async def test_index_email_thread_excludes_soft_deleted_comments():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, display_name="Ann Author")

    email_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="soft_delete_index_test",
        subject="Thread with comments",
        sender="user@example.com",
    )
    email_thread = await EmailThread.get(id=email_message.thread_id)

    await create_email_thread_comment(email_thread_id=email_thread.id, user_id=user.id, content="Kept comment body")
    removed = await create_email_thread_comment(
        email_thread_id=email_thread.id, user_id=user.id, content="Removed comment body"
    )
    await removed.soft_delete()

    await Mailbox.sync(email_thread)
    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    # The kept comment is indexed; the soft-deleted one is excluded from the searchable body
    # (the reverse relation bypasses the NonDeletedManager, so the job filters it explicitly).
    assert "Kept comment body" in content.index_content
    assert "Removed comment body" not in content.index_content


@pytest.mark.asyncio
async def test_index_email_thread_preview_uses_last_message_body():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    first_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="preview_test",
        subject="Retail formulation stability testing",
        sender="alice@example.com",
        body_plain="Initial message about stability testing.",
    )
    email_thread = await EmailThread.get(id=first_message.thread_id)

    await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="preview_test",
        subject="Re: Retail formulation stability testing",
        sender="bob@example.com",
        body_plain=(
            "Hi Alice, Good news. The 12-week accelerated shelf stability tests passed.\r\n\r\n"
            "On Mon, Apr 14, 2026 at 10:00 AM Alice <alice@example.com> wrote:\r\n\r\n"
            "> Initial message about stability testing.\r\n>\r\n"
        ),
    )
    await email_thread.refresh_from_db()
    await Mailbox.sync(email_thread)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None

    # Preview should be the last message body with quotes stripped, not the full indexed content
    assert "12-week accelerated shelf stability tests passed" in content.preview_content
    assert "Email Thread:" not in content.preview_content
    assert "Message count:" not in content.preview_content
    # The quoted original should be stripped from the preview
    assert "Initial message about stability testing" not in content.preview_content

    # Full index_content should still contain everything for search
    assert "Initial message about stability testing" in content.index_content
    assert "12-week accelerated shelf stability tests" in content.index_content


#
# Goal indexing
#


@pytest.mark.asyncio
async def test_index_goal_includes_all_fields():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, name="Goal Creator")
    owner = await create_user(organization_id=organization.id, name="Goal Owner")
    group = await create_group(organization_id=organization.id, name="Engineering Team")

    goal = await create_goal(
        organization_id=organization.id,
        creator_id=user.id,
        owner_id=owner.id,
        group_id=group.id,
        title="Q1 Revenue Target $1m",
        target_date=date(2026, 3, 31),
        start_date=date(2026, 1, 1),
        status=GoalStatus.AT_RISK,
        progress=0.65,
        extras={"source": "Salesforce", "department": "Sales"},
    )
    await create_subgoal(
        parent_id=goal.id,
        organization_id=organization.id,
        creator_id=user.id,
        title="Close Enterprise Deals",
    )
    await create_subgoal(
        parent_id=goal.id,
        organization_id=organization.id,
        creator_id=user.id,
        title="Expand Partner Channel",
    )

    await ContentIndexingJob.from_model(organization.id, goal).perform()

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(goal.global_id))
    content = await Content.get_by_indexing_id(indexing_id).first()

    assert content is not None
    assert content.content_type == ContentType.GOAL
    assert "Q1 Revenue Target $1m" in content.index_content
    assert "Goal Creator" in content.index_content
    assert "Goal Owner" in content.index_content
    assert "Engineering Team" in content.index_content
    assert "2026-03-31" in content.index_content
    assert "2026-01-01" in content.index_content
    assert "at risk" in content.index_content.lower()
    assert "65%" in content.index_content
    assert "source" in content.index_content
    assert "Salesforce" in content.index_content
    assert "department" in content.index_content
    assert "Sales" in content.index_content
    assert "extras" not in content.index_content.lower()
    assert "Close Enterprise Deals" in content.index_content
    assert "Expand Partner Channel" in content.index_content

    goal.completed_at = datetime(2026, 3, 26, tzinfo=UTC)
    await goal.save()
    await ContentIndexingJob.from_model(organization.id, goal).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert "Completed at: 2026-03-26 (5 days early)" in content.index_content

    goal.completed_at = datetime(2026, 3, 31, tzinfo=UTC)
    await goal.save()
    await ContentIndexingJob.from_model(organization.id, goal).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert "Completed at: 2026-03-31 (on target)" in content.index_content

    goal.completed_at = datetime(2026, 4, 3, tzinfo=UTC)
    await goal.save()
    await ContentIndexingJob.from_model(organization.id, goal).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert "Completed at: 2026-04-03 (3 days late)" in content.index_content


@pytest.mark.asyncio
async def test_index_subgoal_independently():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, name="Creator")

    parent = await create_goal(organization_id=organization.id, creator_id=user.id, title="Capacity")
    subgoal = await create_subgoal(
        parent_id=parent.id, organization_id=organization.id, creator_id=user.id, title="Co-pack"
    )

    await ContentIndexingJob.from_model(organization.id, subgoal).perform()
    await ContentIndexingJob.from_model(organization.id, parent).perform()

    subgoal_content = await Content.get_by_indexing_id(
        IndexingID(organization_id=organization.id, source_id=str(subgoal.global_id))
    ).first()
    parent_content = await Content.get_by_indexing_id(
        IndexingID(organization_id=organization.id, source_id=str(parent.global_id))
    ).first()

    assert subgoal_content is not None
    assert subgoal_content.title == "Co-pack"
    assert subgoal_content.content_type == ContentType.GOAL
    assert "Parent goal: Capacity" in subgoal_content.index_content

    assert parent_content is not None
    assert parent_content.title == "Capacity"
    assert "Co-pack" in parent_content.index_content


@pytest.mark.asyncio
async def test_parent_deletion_cleans_up_subgoal_content():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, name="Creator")

    parent = await create_goal(organization_id=organization.id, creator_id=user.id, title="Capacity")
    subgoal = await create_subgoal(
        parent_id=parent.id, organization_id=organization.id, creator_id=user.id, title="Co-pack"
    )

    await ContentIndexingJob.from_model(organization.id, parent).perform()
    await ContentIndexingJob.from_model(organization.id, subgoal).perform()

    parent_indexing_id = IndexingID(organization_id=organization.id, source_id=str(parent.global_id))
    subgoal_indexing_id = IndexingID(organization_id=organization.id, source_id=str(subgoal.global_id))
    assert await Content.get_by_indexing_id(parent_indexing_id).exists()
    assert await Content.get_by_indexing_id(subgoal_indexing_id).exists()

    await parent.soft_delete()
    await subgoal.soft_delete()
    await ContentIndexingJob.from_model(organization.id, parent).perform()

    assert not await Content.get_by_indexing_id(parent_indexing_id).exists()
    assert not await Content.get_by_indexing_id(subgoal_indexing_id).exists()


#
# Chat indexing
#
#


@pytest.mark.asyncio
async def test_index_chat_dm_and_self():
    organization = await create_organization()
    alice = await create_user(organization_id=organization.id, name="Alice")
    bob = await create_user(organization_id=organization.id, name="Bob")

    dm = await create_chat(organization_id=organization.id, title=None)
    await create_collaborator(workspace_id=dm.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=dm.workspace_id, user_id=bob.id)
    await create_chat_message(chat_id=dm.id, user_id=alice.id, content="<p>Hi Bob</p>")
    await create_chat_message(chat_id=dm.id, user_id=bob.id, content="<p>Hey @Alice</p>")

    dm_indexing_id = IndexingID(organization_id=organization.id, source_id=str(dm.global_id))
    await IndexChatJob(indexing_id=dm_indexing_id).perform()

    dm_content = await Content.get_by_indexing_id(dm_indexing_id).first()
    assert dm_content is not None
    assert dm_content.content_type == ContentType.CHAT
    assert dm_content.title == "Alice and Bob"
    assert dm_content.preview_content == "Bob: Hey @Alice"
    assert "Hey @Alice" in dm_content.index_content
    assert dm_content.sharing == Sharing.PRIVATE

    self_chat = await create_chat(organization_id=organization.id, title=None)
    await create_collaborator(workspace_id=self_chat.workspace_id, user_id=alice.id)
    await create_chat_message(chat_id=self_chat.id, user_id=alice.id, content="reminder")

    self_indexing_id = IndexingID(organization_id=organization.id, source_id=str(self_chat.global_id))
    await IndexChatJob(indexing_id=self_indexing_id).perform()

    self_content = await Content.get_by_indexing_id(self_indexing_id).first()
    assert self_content is not None
    assert self_content.title == "Note to self"
    assert self_content.preview_content == "Alice: reminder"


@pytest.mark.asyncio
async def test_index_chat_multi_and_attachment_and_truncation():
    organization = await create_organization()
    alice = await create_user(organization_id=organization.id, name="Alice")
    bob = await create_user(organization_id=organization.id, name="Bob")
    carol = await create_user(organization_id=organization.id, name="Carol")

    multi = await create_chat(organization_id=organization.id, title=None)
    for user in (alice, bob, carol):
        await create_collaborator(workspace_id=multi.workspace_id, user_id=user.id)
    await create_chat_message(chat_id=multi.id, user_id=alice.id, content="Hi all")

    multi_indexing_id = IndexingID(organization_id=organization.id, source_id=str(multi.global_id))
    await IndexChatJob(indexing_id=multi_indexing_id).perform()

    multi_content = await Content.get_by_indexing_id(multi_indexing_id).first()
    assert multi_content is not None
    assert multi_content.title == "Alice, Bob, Carol"

    named_multi = await create_chat(organization_id=organization.id, title="Project Chat")
    for user in (alice, bob, carol):
        await create_collaborator(workspace_id=named_multi.workspace_id, user_id=user.id)
    await create_chat_message(chat_id=named_multi.id, user_id=alice.id, content="kickoff")

    named_indexing_id = IndexingID(organization_id=organization.id, source_id=str(named_multi.global_id))
    await IndexChatJob(indexing_id=named_indexing_id).perform()

    named_content = await Content.get_by_indexing_id(named_indexing_id).first()
    assert named_content is not None
    assert named_content.title == "Project Chat"

    # Attachment-only latest message: blank body falls back to placeholder; long earlier message
    # gets truncated in preview but kept whole in index_content.
    attachment_chat = await create_chat(organization_id=organization.id, title=None)
    await create_collaborator(workspace_id=attachment_chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=attachment_chat.workspace_id, user_id=bob.id)
    long_body = "x" * 500
    await create_chat_message(chat_id=attachment_chat.id, user_id=alice.id, content=long_body)
    await create_chat_message(chat_id=attachment_chat.id, user_id=bob.id, content="")

    attachment_indexing_id = IndexingID(organization_id=organization.id, source_id=str(attachment_chat.global_id))
    await IndexChatJob(indexing_id=attachment_indexing_id).perform()

    attachment_content = await Content.get_by_indexing_id(attachment_indexing_id).first()
    assert attachment_content is not None
    assert attachment_content.preview_content == "Bob: Sent an attachment"
    assert long_body not in attachment_content.index_content

    # Reindex with the long message as the latest to verify truncation.
    await create_chat_message(chat_id=attachment_chat.id, user_id=alice.id, content=long_body)
    await IndexChatJob(indexing_id=attachment_indexing_id).perform()

    attachment_content = await Content.get_by_indexing_id(attachment_indexing_id).first()
    assert attachment_content is not None
    assert attachment_content.preview_content is not None
    assert len(attachment_content.preview_content) <= 200
    assert attachment_content.preview_content.endswith("…")
    assert long_body in attachment_content.index_content


@pytest.mark.asyncio
async def test_index_chat_soft_deleted_chat_removes_content():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    chat = await create_chat(organization_id=organization.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_chat_message(chat_id=chat.id, user_id=user.id, content="A message")

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(chat.global_id))
    await IndexChatJob(indexing_id=indexing_id).perform()
    assert await Content.get_by_indexing_id(indexing_id).exists()

    await chat.soft_delete()
    await IndexChatJob(indexing_id=indexing_id).perform()
    assert not await Content.get_by_indexing_id(indexing_id).exists()


@pytest.mark.asyncio
async def test_index_chat_allowed_user_ids_reflects_members():
    organization = await create_organization()
    alice = await create_user(organization_id=organization.id, name="Alice")
    bob = await create_user(organization_id=organization.id, name="Bob")
    carol = await create_user(organization_id=organization.id, name="Carol")
    chat = await create_chat(organization_id=organization.id, title="Team Chat")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await create_chat_message(chat_id=chat.id, user_id=alice.id, content="Hi")

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(chat.global_id))
    await IndexChatJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert sorted(content.allowed_user_ids) == sorted([str(alice.id), str(bob.id)])

    # Add Carol as a member and reindex
    await create_collaborator(workspace_id=chat.workspace_id, user_id=carol.id)
    await IndexChatJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert sorted(content.allowed_user_ids) == sorted([str(alice.id), str(bob.id), str(carol.id)])

    # Remove Bob and reindex
    await Collaborator.filter(workspace_id=chat.workspace_id, user_id=bob.id).delete()
    await IndexChatJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert sorted(content.allowed_user_ids) == sorted([str(alice.id), str(carol.id)])


@pytest.mark.asyncio
async def test_index_chat_deletion_removes_all_content():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, name="Alice")
    chat = await create_chat(organization_id=organization.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_chat_message(chat_id=chat.id, user_id=user.id, content="Hello")

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(chat.global_id))
    await IndexChatJob(indexing_id=indexing_id).perform()
    await IndexChatHistoryJob(
        chat_id=chat.id, indexing_id=IndexingID(organization_id=organization.id, source_id=str(chat.global_id))
    ).perform()

    assert await Content.get_by_indexing_id(indexing_id).exists()
    research = await Content.filter(organization_id=organization.id, content_type=ContentType.CHAT_HISTORY).all()
    assert len(research) >= 1

    await chat.soft_delete()
    await IndexChatJob(indexing_id=indexing_id).perform()

    assert not await Content.get_by_indexing_id(indexing_id).exists()
    research = await Content.filter(organization_id=organization.id, content_type=ContentType.CHAT_HISTORY).all()
    assert len(research) == 0


@pytest.mark.asyncio
async def test_index_chat_research_creates_chunks():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, name="Alice")
    chat = await create_chat(organization_id=organization.id, title="Team Chat")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    for i in range(10):
        await create_chat_message(chat_id=chat.id, user_id=user.id, content=f"Message {i}")

    await IndexChatHistoryJob(
        chat_id=chat.id, indexing_id=IndexingID(organization_id=organization.id, source_id=str(chat.global_id))
    ).perform()

    chunks = await Content.filter(organization_id=organization.id, content_type=ContentType.CHAT_HISTORY).all()
    assert len(chunks) >= 1
    assert chunks[0].title.startswith("Team Chat")
    assert "Message 0" in chunks[0].index_content
    assert str(user.id) in chunks[0].allowed_user_ids


@pytest.mark.asyncio
async def test_index_chat_research_incremental():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, name="Alice")
    chat = await create_chat(organization_id=organization.id, title="Incremental Chat")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    history_indexing_id = IndexingID(organization_id=organization.id, source_id=str(chat.global_id))

    for i in range(6):
        await create_chat_message(chat_id=chat.id, user_id=user.id, content=f"Batch1 msg {i}")

    await IndexChatHistoryJob(chat_id=chat.id, indexing_id=history_indexing_id).perform()
    chunks_after_first = await Content.filter(
        organization_id=organization.id, content_type=ContentType.CHAT_HISTORY
    ).count()
    assert chunks_after_first >= 1

    # Add more messages and re-index — should not duplicate existing windows
    for i in range(6):
        await create_chat_message(chat_id=chat.id, user_id=user.id, content=f"Batch2 msg {i}")

    await IndexChatHistoryJob(chat_id=chat.id, indexing_id=history_indexing_id).perform()
    chunks_after_second = await Content.filter(
        organization_id=organization.id, content_type=ContentType.CHAT_HISTORY
    ).count()
    # The second batch should produce additional or updated windows, not duplicates
    assert chunks_after_second >= chunks_after_first


@pytest.mark.asyncio
async def test_update_chat_content_access():
    organization = await create_organization()
    alice = await create_user(organization_id=organization.id, name="Alice")
    bob = await create_user(organization_id=organization.id, name="Bob")
    charlie = await create_user(organization_id=organization.id, name="Charlie")
    chat = await create_chat(organization_id=organization.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await create_chat_message(chat_id=chat.id, user_id=alice.id, content="Hello")

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(chat.global_id))
    await IndexChatJob(indexing_id=indexing_id).perform()

    await UpdateChatContentAccessJob(chat_id=chat.id, user_id=charlie.id, action=AccessAction.ADD).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert str(charlie.id) in content.allowed_user_ids

    await UpdateChatContentAccessJob(chat_id=chat.id, user_id=bob.id, action=AccessAction.REMOVE).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert str(bob.id) not in content.allowed_user_ids
    assert str(alice.id) in content.allowed_user_ids


@pytest.mark.asyncio
async def test_invalidate_chat_history_indexing():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, name="Alice")
    chat = await create_chat(organization_id=organization.id, title="History Chat")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    for i in range(10):
        await create_chat_message(chat_id=chat.id, user_id=user.id, content=f"Message {i}")

    await IndexChatHistoryJob(
        chat_id=chat.id, indexing_id=IndexingID(organization_id=organization.id, source_id=str(chat.global_id))
    ).perform()
    chunks = await Content.filter(organization_id=organization.id, content_type=ContentType.CHAT_HISTORY).count()
    assert chunks >= 1

    # Invalidate from the beginning — should remove all windows
    await invalidate_chat_history_indexing(organization.id, str(chat.global_id), chat.created_at)

    chunks = await Content.filter(organization_id=organization.id, content_type=ContentType.CHAT_HISTORY).count()
    assert chunks == 0


#
# Email thread notification indexing
#
#


@pytest.fixture
def notification_sender() -> str:
    # settings.email_from is the app's own outbound address and an operator supplies it, so
    # there's nothing to recognise a thread as our own notification against until it's set.
    # The autouse `custom_settings` fixture restores it after the test.
    settings.email_from = "notifications@example.com"
    return settings.email_from


@pytest.mark.asyncio
async def test_index_email_thread_skips_notification_thread(notification_sender: str):
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    email_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="notification-skip-test",
        subject="New post: Q2 Planning",
        sender=f"Alice <{notification_sender}>",
    )
    email_thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(email_thread)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is None


@pytest.mark.asyncio
async def test_index_email_thread_indexes_notification_thread_with_comments(notification_sender: str):
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    email_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="notification-with-comment-test",
        subject="New post: Q2 Planning",
        sender=f"Alice <{notification_sender}>",
    )
    email_thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(email_thread)
    await create_email_thread_comment(
        workspace_id=email_thread.workspace_id,
        organization_id=organization.id,
        user_id=user.id,
    )

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.content_type == ContentType.EMAIL_THREAD


@pytest.mark.asyncio
async def test_index_email_thread_removes_previously_indexed_notification(notification_sender: str):
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    email_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="previously-indexed-notification-test",
        subject="New post: Q2 Planning",
        sender=f"Alice <{notification_sender}>",
    )
    email_thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(email_thread)

    await create_content(
        organization_id=organization.id,
        source_id=str(email_thread.global_id),
    )

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    existing = await Content.get_by_indexing_id(indexing_id).first()
    assert existing is not None

    await IndexEmailThreadJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is None


@pytest.mark.asyncio
async def test_index_email_thread_metadata_tracks_comment_count_calendar_invite_and_automated_sender():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    first_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="metadata-calendar-test",
        subject="Project kickoff",
        sender="alice@example.com",
        body_plain="Let's meet Tuesday.",
    )
    human_thread = await EmailThread.get(id=first_message.thread_id)

    reply_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="metadata-calendar-test",
        subject="Re: Project kickoff",
        sender="bob@example.com",
        body_plain="Sounds good, invite attached.",
    )

    invite_file = await FileReference.create(
        key="test/invite.ics",
        filename="invite.ics",
        content_type="text/calendar",
        byte_size=256,
        checksum="ics-checksum",
    )
    await EmailAttachment.create(
        email_message_id=reply_message.id,
        thread_id=human_thread.id,
        file_id=invite_file.id,
    )

    await human_thread.refresh_from_db()
    await Mailbox.sync(human_thread)
    await create_email_thread_comment(
        workspace_id=human_thread.workspace_id,
        organization_id=organization.id,
        user_id=user.id,
    )

    human_indexing_id = IndexingID(organization_id=organization.id, source_id=str(human_thread.global_id))
    await IndexEmailThreadJob(indexing_id=human_indexing_id).perform()

    human_content = await Content.get_by_indexing_id(human_indexing_id).first()
    assert human_content is not None
    assert human_content.metadata["comment_count"] == 1
    assert human_content.metadata["has_calendar_invite"] is True
    assert human_content.metadata["is_automated_sender"] is False

    automated_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="metadata-automated-test",
        subject="Build #42 failed",
        sender="github-actions@github.com",
        body_plain="Your build failed.",
    )
    automated_thread = await EmailThread.get(id=automated_message.thread_id)
    await Mailbox.sync(automated_thread)

    automated_indexing_id = IndexingID(organization_id=organization.id, source_id=str(automated_thread.global_id))
    await IndexEmailThreadJob(indexing_id=automated_indexing_id).perform()

    automated_content = await Content.get_by_indexing_id(automated_indexing_id).first()
    assert automated_content is not None
    assert automated_content.metadata["comment_count"] == 0
    assert automated_content.metadata["has_calendar_invite"] is False
    assert automated_content.metadata["is_automated_sender"] is True


#
# Reaction count indexing
#


async def _add_reaction(comment, user_id, reaction_type: ReactionType) -> None:
    comment.toggle_reaction(user_id, reaction_type)
    await comment.save(update_fields=["reactions"])


@pytest.mark.asyncio
async def test_index_post_includes_reaction_count_across_comments():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    reacter_one = await create_user(organization_id=organization.id)
    reacter_two = await create_user(organization_id=organization.id)

    post = await create_post(organization_id=organization.id, creator_id=creator.id)
    await post.fetch_related("comments")
    initial_comment = post.comments[0]
    await _add_reaction(initial_comment, reacter_one.id, ReactionType.THUMBS_UP)
    await _add_reaction(initial_comment, reacter_two.id, ReactionType.HEART)

    reply = await create_post_comment(post_id=post.id, user_id=reacter_one.id)
    await _add_reaction(reply, reacter_two.id, ReactionType.ROCKET)

    await ContentIndexingJob.from_model(organization.id, post).perform()

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(post.global_id))
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.metadata["reaction_count"] == 3


@pytest.mark.asyncio
async def test_index_goal_includes_reaction_count_across_comments():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    reacter = await create_user(organization_id=organization.id)

    goal = await create_goal(organization_id=organization.id, creator_id=creator.id)
    comment_one = await create_goal_comment(goal_id=goal.id, user_id=creator.id)
    await _add_reaction(comment_one, reacter.id, ReactionType.THUMBS_UP)
    await _add_reaction(comment_one, creator.id, ReactionType.PARTY_POPPER)

    comment_two = await create_goal_comment(goal_id=goal.id, user_id=reacter.id)
    await _add_reaction(comment_two, creator.id, ReactionType.HEART)

    await ContentIndexingJob.from_model(organization.id, goal).perform()

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(goal.global_id))
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.metadata["reaction_count"] == 3


@pytest.mark.asyncio
async def test_index_document_includes_reaction_count_across_comments():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    reacter = await create_user(organization_id=organization.id)

    document = await create_document(organization_id=organization.id, creator_id=creator.id)
    await LiveDocument.set_initial_content(document.live_document_topic, "Document body text.")
    comment = await DocumentComment.create(
        content="Looks good",
        quoted_text="text",
        comment_mark_id="mark-1",
        document_id=document.id,
        user_id=creator.id,
    )
    await _add_reaction(comment, reacter.id, ReactionType.THUMBS_UP)
    await _add_reaction(comment, creator.id, ReactionType.THUMBS_UP)

    await ContentIndexingJob.from_model(organization.id, document).perform()

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(document.global_id))
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.metadata["reaction_count"] == 2


@pytest.mark.asyncio
async def test_index_meeting_uses_live_agenda_over_stale_text_field():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)

    meeting = await create_meeting(organization_id=organization.id, creator_id=creator.id)
    # The text field is only written by an explicit HTTP PATCH; the collaborative editor writes the
    # live doc. Indexing must reflect the live agenda, not this stale field.
    meeting.agenda = "STALE AGENDA TEXT"
    await meeting.save()
    await LiveDocument.set_initial_content(meeting.agenda_topic, "# Live Agenda\nDiscuss quarterly goals")

    await ContentIndexingJob.from_model(organization.id, meeting).perform()

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(meeting.global_id))
    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert "quarterly goals" in content.index_content
    assert "STALE AGENDA TEXT" not in content.index_content


@pytest.mark.asyncio
async def test_index_email_thread_includes_reaction_count_from_email_thread_comments():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    reacter = await create_user(organization_id=organization.id)

    email_message = await create_email_message(
        user_id=user.id,
        organization_id=organization.id,
        external_thread_id="reaction-count-test",
        subject="Discussion",
        sender="alice@example.com",
    )
    email_thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(email_thread)

    comment = await create_email_thread_comment(
        workspace_id=email_thread.workspace_id,
        organization_id=organization.id,
        user_id=user.id,
    )
    await _add_reaction(comment, reacter.id, ReactionType.ROCKET)
    await _add_reaction(comment, user.id, ReactionType.EYES)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(email_thread.global_id))
    await IndexEmailThreadJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.metadata["reaction_count"] == 2


@pytest.mark.asyncio
async def test_index_chat_includes_reaction_count_across_messages():
    organization = await create_organization()
    alice = await create_user(organization_id=organization.id, name="Alice")
    bob = await create_user(organization_id=organization.id, name="Bob")
    chat = await create_chat(organization_id=organization.id, title="Project Chat")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)

    first_message = await create_chat_message(chat_id=chat.id, user_id=alice.id, content="Hi")
    await _add_reaction(first_message, bob.id, ReactionType.THUMBS_UP)

    second_message = await create_chat_message(chat_id=chat.id, user_id=bob.id, content="Hey")
    await _add_reaction(second_message, alice.id, ReactionType.HEART)
    await _add_reaction(second_message, bob.id, ReactionType.PARTY_POPPER)

    indexing_id = IndexingID(organization_id=organization.id, source_id=str(chat.global_id))
    await IndexChatJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content is not None
    assert content.metadata["reaction_count"] == 3


#
# Content lookup dual-write
#
#


@pytest.mark.asyncio
@pytest.mark.disable_vcr
async def test_sync_content_lookup_creates_lookup_entry():
    content = await create_content(title="Lookup Test", author="Alice Smith")
    indexer = ContentIndexer(content)
    await indexer._sync_content_lookup()

    lookup = await ContentLookup.get_or_none(content_id=content.id)
    assert lookup is not None
    assert lookup.title == content.title
    assert lookup.title_normalized == content.title_normalized
    assert lookup.author == content.author
    assert lookup.author_normalized == content.author_normalized
    assert lookup.content_type == content.content_type
    assert lookup.sharing == content.sharing
    assert lookup.organization_id == content.organization_id
    assert lookup.source_id == content.source_id
    assert lookup.source_url == content.source_url


@pytest.mark.asyncio
@pytest.mark.disable_vcr
async def test_sync_content_lookup_updates_existing_entry():
    content = await create_content(title="Original Title")
    indexer = ContentIndexer(content)
    await indexer._sync_content_lookup()

    lookup = await ContentLookup.get_or_none(content_id=content.id)
    assert lookup is not None
    assert lookup.title == "Original Title"

    content.title = "Updated Title"
    content.title_normalized = "updated title"
    await content.save()
    await indexer._sync_content_lookup()

    await lookup.refresh_from_db()
    assert lookup.title == "Updated Title"


@pytest.mark.asyncio
@pytest.mark.disable_vcr
async def test_content_deletion_cascades_to_content_lookup():
    content = await create_content(title="To Be Deleted")
    indexer = ContentIndexer(content)
    await indexer._sync_content_lookup()

    lookup = await ContentLookup.get_or_none(content_id=content.id)
    assert lookup is not None

    await content.delete()
    lookup = await ContentLookup.get_or_none(content_id=content.id)
    assert lookup is None
