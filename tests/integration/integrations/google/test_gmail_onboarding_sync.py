import pytest

from app.jobs.onboarding import CompleteOnboardingMailboxSyncJob
from app.models.accounts import OAuthToken
from app.models.workspaces.email.thread import EmailMessage, EmailThread
from config.enums import AuthenticationProvider, ChannelMessageType, Integration
from infra.jobs import InlineJobs, JobsOutbox
from infra.messaging import Topic
from integrations.google.gmail import MockGmailAPIState
from integrations.google.jobs.gmail_onboarding_sync import (
    ONBOARDING_SYNC_QUERIES,
    OnboardingMailboxSyncGmailJob,
    ProgressiveThreadMessageSyncJob,
)
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES
from tests.helpers.app import AppClient
from tests.helpers.factories import create_gmail_account, create_research_question, create_user
from tests.integration.integrations.google.conftest import add_gmail_token_to_user


@pytest.mark.asyncio
async def test_gmail_onboarding_sync(client: AppClient, gmail_state: MockGmailAPIState):
    """Test Gmail onboarding sync job by setting up mock messages and threads"""
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    # Set up OAuth token with Gmail scopes
    user_token = await OAuthToken.get_or_none(user_id=user.id)
    assert user_token is not None
    user_token.scope = user_token.scope + ",".join(GOOGLE_GMAIL_SCOPES)
    user_token.provider = AuthenticationProvider.GOOGLE
    await user_token.save()

    gmail_account = await create_gmail_account(history_id="2000", user_id=user.id, email=user.email)

    # Set up mock Gmail API state
    gmail_state.set_profile(gmail_account)

    # Use simplified builder methods to create test messages
    gmail_state.add_message(
        "msg_inbox_1",
        "thread_1",
        email=gmail_account.email,
        labels=["INBOX", "UNREAD"],
        headers={
            "Subject": "Important Meeting",
            "From": "boss@company.com",
            "To": user.email,
        },
        body_plain="Please review the quarterly reports before tomorrow's meeting.",
    )

    gmail_state.add_message(
        "msg_sent_1",
        "thread_2",
        email=gmail_account.email,
        labels=["SENT"],
        headers={
            "Subject": "Project Update",
            "From": user.email,
            "To": "colleague@company.com",
        },
        body_plain="The project is on track for delivery next week.",
    )

    gmail_state.add_message(
        "msg_archived_1",
        "thread_3",
        email=gmail_account.email,
        labels=[],
        headers={
            "Subject": "Archived Newsletter",
            "From": "newsletter@example.com",
            "To": user.email,
        },
        body_plain="This week's newsletter content...",
    )

    # Create a conversation thread with reply
    gmail_state.add_message(
        "msg_conversation_1",
        "thread_4",
        email=gmail_account.email,
        labels=["INBOX"],
        headers={
            "Subject": "Client Inquiry",
            "From": "client@external.com",
            "To": user.email,
        },
        body_plain="Can we schedule a call to discuss the proposal?",
    )

    gmail_state.add_message(
        "msg_conversation_2",
        "thread_4",
        email=gmail_account.email,
        labels=["INBOX"],
        headers={
            "Subject": "Re: Client Inquiry",
            "From": user.email,
            "To": "client@external.com",
            "In-Reply-To": "<msg_conversation_1@example.com>",
            "References": "<msg_conversation_1@example.com>",
        },
        body_plain="Sure, how about Thursday at 2pm?",
    )

    # Run Gmail onboarding sync job to import all messages
    async with JobsOutbox():
        onboarding_sync_job = OnboardingMailboxSyncGmailJob(user_id=user.id)
        await onboarding_sync_job.perform()

    # Verify onboarding sync completed successfully
    await gmail_account.refresh_from_db()
    assert gmail_account.onboarding_mailbox_sync_started_at is not None
    assert gmail_account.onboarding_mailbox_sync_completed_at is not None

    # Verify history_id advanced to the max historyId from processed messages (mock uses "67890")
    assert gmail_account.history_id == "67890"

    email_threads = await EmailThread.filter(creator_id=user.id).all().prefetch_related("messages")
    assert len(email_threads) == 4

    # Check inbox message
    inbox_thread = next((t for t in email_threads if t.title == "Important Meeting"), None)
    assert inbox_thread is not None
    inbox_messages = await inbox_thread.messages
    assert len(inbox_messages) == 1
    inbox_msg = inbox_messages[0]
    assert inbox_msg.sender_address.email == "boss@company.com"
    assert "quarterly reports" in inbox_msg.body_plain
    assert inbox_msg.is_inbox
    assert not inbox_msg.is_read
    # Note: IMPORTANT label not supported in EmailLabel enum

    # Check sent message
    sent_thread = next((t for t in email_threads if t.title == "Project Update"), None)
    assert sent_thread is not None
    sent_messages = await sent_thread.messages
    assert len(sent_messages) == 1
    sent_msg = sent_messages[0]
    assert sent_msg.sender_address.email == user.email
    assert "on track for delivery" in sent_msg.body_plain
    assert sent_msg.is_sent
    assert not sent_msg.is_inbox

    # Check conversation thread (should have 2 messages)
    conversation_thread = next((t for t in email_threads if t.title == "Client Inquiry"), None)
    assert conversation_thread is not None
    conversation_messages = await conversation_thread.messages
    assert len(conversation_messages) == 2

    original_msg = next((m for m in conversation_messages if "schedule a call" in m.body_plain), None)
    reply_msg = next((m for m in conversation_messages if "Thursday at 2pm" in m.body_plain), None)
    assert original_msg is not None
    assert reply_msg is not None
    assert original_msg.sender_address.email == "client@external.com"
    assert reply_msg.sender_address.email == user.email


@pytest.mark.asyncio
async def test_no_thread_message_sync_for_forwards(
    client: AppClient, background_jobs: InlineJobs, gmail_state: MockGmailAPIState
):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="1000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    # Test case: Forwarded email with In-Reply-To header does NOT trigger thread message sync because
    # is_reply should correctly identify it as NOT a reply
    # (Even though it has In-Reply-To, the "Fwd:" prefix should take precedence)
    gmail_state.add_message(
        "msg_forward",
        "thread_forward",
        email=gmail_account.email,
        labels=["INBOX"],
        headers={
            "Subject": "Fwd: Important Announcement",
            "From": user.email,
            "To": "team@company.com",
            "Message-Id": "<forward@example.com>",
            "In-Reply-To": "<announcement@example.com>",  # Has In-Reply-To but is a forward
        },
        body_plain="FYI - please review this announcement.",
    )

    await gmail_state.trigger_gmail_webhooks(client)

    thread_message_sync_jobs = background_jobs.all_completed_jobs_by_type(ProgressiveThreadMessageSyncJob)
    assert len(thread_message_sync_jobs) == 0
    forward_thread = await EmailThread.get_or_none(creator_id=user.id, external_thread_id="thread_forward")
    assert forward_thread is not None
    forward_messages = await EmailMessage.filter(thread_id=forward_thread.id).all()
    assert len(forward_messages) == 1
    forward_msg = forward_messages[0]
    assert not forward_msg.is_reply


@pytest.mark.asyncio
async def test_onboarding_sync_broadcasts_inbox_progress_on_first_run(
    client: AppClient, gmail_state: MockGmailAPIState
):
    """The mailbox page renders before the worker picks up the onboarding job,
    so the syncing banner is absent on first paint. The first run of the job
    must broadcast on `inbox_progress` so the React banner + progress dropdown
    update without a refresh. See `app/routers/api/inbox_progress.py`.
    """
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="1000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    topic = Topic("inbox_progress", user_id=user.id)
    async with client.connect_channel(topic) as websocket:
        await OnboardingMailboxSyncGmailJob(user_id=user.id).perform()

        # The HTML inbox_progress handler was removed; only the JSON event handler fires.
        message = await websocket.receive_json(timeout=2)
        assert message["type"] == ChannelMessageType.EVENT


@pytest.mark.real_embeddings
@pytest.mark.asyncio
async def test_onboarding_sync_completion_starts_pending_research(
    background_jobs: InlineJobs, gmail_state: MockGmailAPIState
):
    """Onboarding sync completion triggers pending research to start"""
    user = await create_user()
    await user.add_integration(Integration.GMAIL)
    await user.fetch_related("organization")

    user_token = await OAuthToken.get_or_none(user_id=user.id)
    assert user_token is not None
    user_token.scope = user_token.scope + "," + ",".join(GOOGLE_GMAIL_SCOPES)
    user_token.provider = AuthenticationProvider.GOOGLE
    await user_token.save()

    gmail_account = await create_gmail_account(history_id="2000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    command = await create_research_question(creator_id=user.id)
    assert command.status.is_pending
    assert command.research_id is None

    # Complete onboarding sync - InlineJobs fixture will run enqueued jobs immediately
    async with JobsOutbox():
        job = OnboardingMailboxSyncGmailJob(user_id=user.id, current_query_index=len(ONBOARDING_SYNC_QUERIES))
        await job.perform()

    # Verify CompleteOnboardingMailboxSyncJob was enqueued and ran
    assert background_jobs.has_completed_job(CompleteOnboardingMailboxSyncJob)

    # Verify user onboarding mailbox sync timestamps are set
    await user.refresh_from_db()
    assert user.onboarding_mailbox_sync_started_at is not None
    assert user.onboarding_mailbox_sync_completed_at is not None


@pytest.mark.real_embeddings
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_onboarding_sync_completion_handles_multiple_pending_research(
    background_jobs: InlineJobs, gmail_state: MockGmailAPIState
):
    """Onboarding sync completion starts all pending research commands"""
    user = await create_user()
    await user.add_integration(Integration.GMAIL)
    await user.fetch_related("organization")

    user_token = await OAuthToken.get_or_none(user_id=user.id)
    assert user_token is not None
    user_token.scope = user_token.scope + "," + ",".join(GOOGLE_GMAIL_SCOPES)
    user_token.provider = AuthenticationProvider.GOOGLE
    await user_token.save()

    gmail_account = await create_gmail_account(history_id="2000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    await create_research_question(creator_id=user.id)
    await create_research_question(creator_id=user.id)

    # Complete onboarding sync - InlineJobs fixture will run enqueued jobs immediately
    async with JobsOutbox():
        job = OnboardingMailboxSyncGmailJob(user_id=user.id, current_query_index=len(ONBOARDING_SYNC_QUERIES))
        await job.perform()

    # Verify CompleteOnboardingMailboxSyncJob was enqueued and ran
    assert background_jobs.has_completed_job(CompleteOnboardingMailboxSyncJob)

    # Verify user onboarding mailbox sync timestamps are set
    await user.refresh_from_db()
    assert user.onboarding_mailbox_sync_started_at is not None
    assert user.onboarding_mailbox_sync_completed_at is not None
