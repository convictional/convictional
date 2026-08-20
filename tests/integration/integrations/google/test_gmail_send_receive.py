from pathlib import Path

import pytest
from fastapi import status

from app.models.collaboration.mailbox import MailboxEntry
from app.models.workspaces.email.thread import EmailThread
from config.enums import Integration
from infra.jobs import InlineJobs
from integrations.google.gmail import MockGmailAPIState
from integrations.google.jobs.gmail import SendEmailThroughGmailJob
from tests.helpers.app import AppClient
from tests.helpers.factories import create_gmail_account, create_user
from tests.integration.integrations.google.conftest import add_gmail_token_to_user


@pytest.mark.asyncio
async def test_email_flow(client: AppClient, background_jobs: InlineJobs, gmail_state: MockGmailAPIState):
    user_1 = await client.get_default_user()
    await user_1.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user_1)

    user_2 = await create_user(organization_id=user_1.organization_id)
    await user_2.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user_2)

    gmail_account_1 = await create_gmail_account(history_id="1000", user_id=user_1.id, email=user_1.email)
    gmail_account_2 = await create_gmail_account(history_id="1000", user_id=user_2.id, email=user_2.email)

    # Set up mock Gmail API state
    gmail_state.set_profile(gmail_account_1)
    gmail_state.set_profile(gmail_account_2)

    # User 1 creates an email
    with client.current_user_as(user_1):
        response = await client.post("/api/email_threads")
        assert response.status_code == status.HTTP_201_CREATED
        email_thread = await EmailThread.all().first()
        assert email_thread is not None

        # Compose the draft
        response = await client.patch(
            f"/api/email_threads/{email_thread.id}/draft",
            json={
                "to": [user_2.email],
                "subject": "Test Email",
            },
        )
        assert response.status_code == 204
        draft = await email_thread.get_draft()
        assert draft is not None
        assert draft.to == user_2.email
        assert draft.subject == "Test Email"

        # Send the draft via the router - this will use Gmail client and enqueue SendEmailThroughGmailJob
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/draft/send",
            json={
                "to": [user_2.email],
                "subject": "Test Email",
                "message_body": (
                    "Hello,\n\nThis is a **test** email sent from the integration tests.\n\nBest regards,\nUser 1"
                ),
            },
        )
        assert response.status_code == 204
        assert background_jobs.has_completed_job(SendEmailThroughGmailJob)

        sent_message = draft.message
        await sent_message.refresh_from_db()

        assert sent_message.is_sent
        assert sent_message.sent_at is not None
        assert sent_message.sent_from_convictional_at is not None
        assert sent_message.subject == "Test Email"
        assert sent_message.to == [user_2.email]
        assert "This is a test email" in sent_message.body_plain
        assert "<strong>test</strong>" in sent_message.body_html

    # Manually trigger webhook processing
    await gmail_state.trigger_gmail_webhooks(client)

    # User 2 has received the email
    with client.current_user_as(user_2):
        email_threads = await EmailThread.filter(creator_id=user_2.id).all().prefetch_related("messages")
        assert len(email_threads) == 1
        email_thread = email_threads[0]
        assert email_thread is not None
        assert email_thread.title == "Test Email"
        messages = await email_thread.messages
        assert len(messages) == 1
        received_message = messages[0]
        assert received_message is not None
        assert received_message.subject == "Test Email"
        assert received_message.sender_address.email == user_1.email
        assert "This is a test email" in received_message.body_plain
        assert "<strong>test</strong>" in received_message.body_html
        assert received_message.to == [user_2.email]
        assert received_message.is_inbox
        assert not received_message.is_sent
        assert received_message.sent_from_convictional_at is None
        assert not received_message.is_read
        assert received_message.id != sent_message.id
        assert received_message.message_id == sent_message.message_id  # Same email, different users

        # Message is in the inbox
        response = await client.get("/api/mailbox_entries?view=inbox")
        assert response.status_code == 200
        assert any(item["title"] == "Test Email" for item in response.json()["entries"])

        # Show the message
        response = await client.get(f"/api/email_threads/{email_thread.id}")
        assert response.status_code == 200
        assert response.json()["thread"]["title"] == "Test Email"

        # Mark the message as read
        mailbox_entry = await MailboxEntry.get(resource_gid=str(email_thread.global_id), owner_id=user_2.id)
        response = await client.post(f"/api/mailbox_entries/{mailbox_entry.id}/mark_read")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        await received_message.refresh_from_db()
        assert received_message.is_read

        # Reply to the message
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{received_message.id}/reply",
            json={"reply_type": "reply"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        reply_draft = await email_thread.get_draft()
        assert reply_draft is not None
        assert user_1.email in reply_draft.to
        assert reply_draft.subject == "Re: Test Email"
        assert reply_draft.in_reply_to == received_message.message_id

        # Send the reply
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/draft/send",
            json={
                "to": [user_1.email],
                "subject": "Re: Test Email",
                "message_body": "Thanks for your email, User 1!\n\nBest,\nUser 2",
            },
        )
        assert response.status_code == 204
        reply_message = reply_draft.message
        await reply_message.refresh_from_db()
        assert reply_message.is_sent
        assert reply_message.sent_at is not None

    # Manually trigger webhook processing for the reply
    await gmail_state.trigger_gmail_webhooks(client)

    # User 1 receives the reply
    with client.current_user_as(user_1):
        email_threads = await EmailThread.filter(creator_id=user_1.id).all().prefetch_related("messages")
        assert len(email_threads) == 1
        email_thread = email_threads[0]
        assert email_thread is not None
        assert email_thread.title == "Test Email"
        messages = await email_thread.messages
        assert len(messages) == 2

        # Find the received reply message (not the originally sent message)
        received_reply_message = next(msg for msg in messages if not msg.is_sent)
        assert received_reply_message is not None

        assert received_reply_message.subject == "Re: Test Email"
        assert received_reply_message.sender_address.email == user_2.email
        assert "Thanks for your email" in received_reply_message.body_plain
        assert received_reply_message.to == [user_1.email]
        assert received_reply_message.is_inbox
        assert not received_reply_message.is_sent  # Because User 2 sent the reply
        assert not received_reply_message.is_read  # Not read until User 1 views it
        assert received_reply_message.message_id != sent_message.message_id  # Different email
        assert received_reply_message.id != reply_message.id  # Different EmailMessage
        assert received_reply_message.message_id == reply_message.message_id  # Same email, different users

        # Thread is back in the inbox
        response = await client.get("/api/mailbox_entries?view=inbox")
        assert response.status_code == 200
        assert any(item["title"] == "Test Email" for item in response.json()["entries"])

        # Read the reply. The timeline is a metadata-only summary, so fetch each
        # message's body from its content sub-resource.
        response = await client.get(f"/api/email_threads/{email_thread.id}")
        assert response.status_code == 200
        message_ids = [item["message"]["id"] for item in response.json()["timeline"] if item["type"] == "message"]
        message_bodies = ""
        for message_id in message_ids:
            content = await client.get(f"/api/email_threads/{email_thread.id}/email_messages/{message_id}/content")
            assert content.status_code == 200
            message_bodies += content.json()["content_html"]
        assert "Thanks for your email" in message_bodies


@pytest.mark.asyncio
async def test_receiving_inline_images(client: AppClient, background_jobs: InlineJobs, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="0", user_id=user.id, email=user.email)

    # Set up mock Gmail API state
    gmail_state.set_profile(gmail_account)

    # Add a message with inline images
    gmail_state.load_threads_from_directory(
        Path().cwd() / "tests" / "fixtures" / "email_threads" / "test_inline_images", user.email
    )

    # Manually trigger webhook processing
    await gmail_state.trigger_gmail_webhooks(client)

    email_threads = await EmailThread.filter(creator_id=user.id).prefetch_related("messages__attachments__file").all()

    assert len(email_threads) == 1
    email_thread = email_threads[0]
    assert email_thread is not None
    messages = await email_thread.messages
    assert len(messages) == 1
    received_message = messages[0]
    assert received_message is not None

    attachments = await received_message.attachments
    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment is not None
    assert attachment.is_inline
    assert attachment.content_id is not None
    assert attachment.file is not None

    file = await attachment.file

    with client.current_user_as(user):
        response = await client.get(
            f"/api/email_threads/{email_thread.id}/email_messages/{received_message.id}/content"
        )
        assert response.status_code == 200
        body = response.json()
        # The inline image should be referenced in the HTML body, not the CID
        assert file.filename in body["content_html"]
        assert attachment.content_id not in body["content_html"]
