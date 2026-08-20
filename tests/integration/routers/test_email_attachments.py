import io
from email import message_from_string
from urllib.parse import urljoin
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from fastapi import status
from pycrdt import Text

from app.models.collaboration.live import LiveDocument, LiveDocumentUpdate
from app.models.collaboration.mailbox import Mailbox
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.client import FakeEmailClient
from app.models.workspaces.email.thread import EmailAttachment, EmailDraft, EmailThread
from app.routers.email_attachments import signed_attachment_download_url
from config import settings
from config.enums import EmailMessageType
from infra.email import EmailHeaders, sign_attachment_download_token
from infra.storage import store_file
from integrations.google.email_mime_builder import MAX_TOTAL_ATTACHMENT_SIZE, EmailMimeBuilder
from tests.helpers.app import AppClient
from tests.helpers.factories import create_email_draft, create_email_message, create_user


@pytest.mark.asyncio
async def test_email_message_attachments(client: AppClient, email_client: FakeEmailClient):
    superuser = await create_user()
    client.current_user = superuser

    email_draft = await create_email_draft(
        user_id=superuser.id,
        organization_id=superuser.organization_id,
        subject="Email with Attachment",
        body_plain="This email has an attachment",
        to=["recipient@example.com"],
    )
    email_thread = email_draft.thread

    # Test successful upload
    test_file_content = b"This is a test attachment"
    test_file = io.BytesIO(test_file_content)

    upload_response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/attachments",
        files={"files": ("test.txt", test_file, "text/plain")},
    )
    assert upload_response.status_code == status.HTTP_200_OK

    # Verify attachment was created
    attachment = await EmailAttachment.first().prefetch_related("file")
    assert attachment is not None
    assert attachment.email_message_id == email_draft.id
    assert attachment.file.filename == "test.txt"
    assert await attachment.file.download() == test_file_content

    # Test download (redirects are followed automatically by test client)
    download_response = await client.get(
        f"/email_threads/{email_draft.thread_id}/attachments/{attachment.id}/download"
    )
    assert download_response.status_code == status.HTTP_200_OK

    # Reload draft with attachments before MIME generation
    email_draft_optional = await email_thread.get_draft()
    assert email_draft_optional is not None
    email_draft = email_draft_optional

    # Store live document markdown before MIME generation
    live_document_markdown = await email_draft.get_live_document_markdown()
    email_draft.message.body_markdown = live_document_markdown
    await email_draft.save()

    # Test MIME generation includes attachment
    mime_string = await EmailMimeBuilder.build_mime_string_from_draft(email_draft)

    # Parse the MIME message to check structure
    msg = message_from_string(mime_string)

    # Verify it's a multipart/mixed message
    assert msg.get_content_type() == "multipart/mixed"

    # Find attachment parts and verify test.txt is included
    attachment_parts = []
    for part in msg.walk():
        content_disposition = part.get("Content-Disposition", "")
        if content_disposition.startswith("attachment"):
            attachment_parts.append(part)

    # Extract filenames from attachment parts
    included_filenames = []
    for part in attachment_parts:
        content_disposition = part.get("Content-Disposition", "")
        if "filename=" in content_disposition:
            # Extract filename from Content-Disposition header
            filename = content_disposition.split("filename=")[1].strip('"')
            included_filenames.append(filename)

    assert "test.txt" in included_filenames

    # Non-existent attachment
    response = await client.get(f"/email_threads/{email_draft.thread_id}/attachments/{uuid4()}/download")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Non-existent email - we need a valid thread_id to test 404, but let's use email_draft's thread
    # Delete the draft so we don't get it by thread_id
    await email_thread.remove_draft(superuser)
    response = await client.post(
        f"/api/email_threads/{email_draft.thread_id}/draft/attachments",
        files={"files": ("test2.txt", io.BytesIO(b"test"), "text/plain")},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_multiple_file_upload(client: AppClient, email_client: FakeEmailClient):
    """Test uploading multiple files at once"""
    superuser = await create_user()
    client.current_user = superuser

    email_draft = await create_email_draft(
        user_id=superuser.id,
        organization_id=superuser.organization_id,
        subject="Email with Multiple Attachments",
        body_plain="This email has multiple attachments",
        to=["recipient@example.com"],
    )
    email_thread = email_draft.thread

    # Upload multiple files at once
    test_files = [
        ("files", ("test1.txt", io.BytesIO(b"Content 1"), "text/plain")),
        ("files", ("test2.txt", io.BytesIO(b"Content 2"), "text/plain")),
        ("files", ("test3.txt", io.BytesIO(b"Content 3"), "text/plain")),
    ]

    upload_response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/attachments",
        files=test_files,
    )
    assert upload_response.status_code == status.HTTP_200_OK

    # Verify all attachments were created
    attachments = await EmailAttachment.filter(email_message_id=email_draft.id).prefetch_related("file")
    assert len(attachments) == 3

    filenames = {att.file.filename for att in attachments}
    assert filenames == {"test1.txt", "test2.txt", "test3.txt"}

    # Verify content
    for attachment in attachments:
        content = await attachment.file.download()
        if attachment.file.filename == "test1.txt":
            assert content == b"Content 1"
        elif attachment.file.filename == "test2.txt":
            assert content == b"Content 2"
        elif attachment.file.filename == "test3.txt":
            assert content == b"Content 3"


@pytest.mark.asyncio
async def test_attachment_size_with_download_fallback(client: AppClient, email_client: FakeEmailClient):
    """Test max attachment size limits with download link fallback functionality"""
    superuser = await create_user()
    client.current_user = superuser

    # Create a draft email
    email_draft = await create_email_draft(
        user_id=superuser.id,
        organization_id=superuser.organization_id,
        subject="Test Max Attachment Size",
        body_plain="This email tests attachment size limits",
        to=["recipient@example.com"],
    )
    email_thread = email_draft.thread
    await Mailbox.sync(email_thread)

    # Create attachments of various sizes
    small_file_content = b"Small file content" * 100  # ~1.8KB
    medium_file_content = b"Medium file content" * 100_000  # ~1.9MB
    large_file_content = b"Large file content" * 1_000_000  # ~18MB (exceeds 5MB limit)

    # Upload small file (should be attached)
    small_file = io.BytesIO(small_file_content)
    upload_response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/attachments",
        files={"files": ("small.txt", small_file, "text/plain")},
    )
    assert upload_response.status_code == status.HTTP_200_OK

    # Upload medium file (should be attached)
    medium_file = io.BytesIO(medium_file_content)
    upload_response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/attachments",
        files={"files": ("medium.txt", medium_file, "text/plain")},
    )
    assert upload_response.status_code == status.HTTP_200_OK

    # Upload large file (should be replaced with download link)
    large_file = io.BytesIO(large_file_content)
    upload_response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/attachments",
        files={"files": ("large.txt", large_file, "text/plain")},
    )
    assert upload_response.status_code == status.HTTP_200_OK

    # Verify all attachments were created in database
    attachments = await EmailAttachment.filter(email_message_id=email_draft.id).prefetch_related(
        "file", "email_message"
    )
    assert len(attachments) == 3

    # Verify attachment properties
    attachment_map = {att.file.filename: att for att in attachments}

    small_attachment = attachment_map["small.txt"]
    assert small_attachment.file.byte_size == len(small_file_content)
    small_payload = await small_attachment.as_payload()
    assert not small_payload.is_oversized

    medium_attachment = attachment_map["medium.txt"]
    assert medium_attachment.file.byte_size == len(medium_file_content)
    medium_payload = await medium_attachment.as_payload()
    assert not medium_payload.is_oversized

    large_attachment = attachment_map["large.txt"]
    assert large_attachment.file.byte_size == len(large_file_content)
    large_payload = await large_attachment.as_payload()
    assert large_payload.is_oversized

    # Verify download URLs are generated for all attachments
    for attachment in attachments:
        download_url = attachment._download_url()
        assert download_url is not None
        expected = urljoin(
            str(settings.base_url),
            f"email_threads/{email_draft.thread_id}/attachments/{attachment.id}/download",
        )
        assert expected == download_url

    # Reload draft with attachments before sending
    await email_draft.refresh_from_db()
    await email_draft.fetch_related("attachments__file")

    # Set up live document content for validation
    topic = email_draft.live_document_topic
    live_doc = await LiveDocument.for_topic(topic)
    markdown_text = live_doc.get("markdown", type=Text)
    markdown_text.insert(0, email_draft.message.body_plain)
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=live_doc.get_update())

    # Test sending the email to verify MIME processing with size limits
    response = await client.post(
        f"/api/email_threads/{email_draft.thread_id}/draft/send",
        json={
            "subject": email_draft.message.subject,
            "to": email_draft.message.to,
            "message_body": email_draft.message.body_plain,
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Reload draft with updated content after sending
    await email_draft.refresh_from_db()
    await email_draft.fetch_related("attachments__file")

    # Verify email was sent
    assert email_draft.message.was_sent

    # Test MIME generation to verify attachment processing
    mime_string = await EmailMimeBuilder.build_mime_string_from_draft(email_draft)

    # Parse the MIME message to check actual attachment parts
    mime_message = message_from_string(mime_string)

    # Find all attachment parts (excluding inline parts and body parts)
    attachment_parts = []
    for part in mime_message.walk():
        content_disposition = part.get("Content-Disposition", "")
        if content_disposition.startswith("attachment"):
            attachment_parts.append(part)

    # Extract filenames from attachment parts
    included_filenames = []
    for part in attachment_parts:
        content_disposition = part.get("Content-Disposition", "")
        if "filename=" in content_disposition:
            # Extract filename from Content-Disposition header
            filename = content_disposition.split("filename=")[1].strip('"')
            included_filenames.append(filename)

    # Verify MIME structure includes small and medium attachments
    assert "small.txt" in included_filenames
    assert "medium.txt" in included_filenames

    # Verify large attachment is excluded from MIME (size limits working)
    assert "large.txt" not in included_filenames

    # Verify that the payload processing correctly identifies oversized attachments
    # and that download URLs are available
    assert large_payload.is_oversized
    assert large_payload.download_url is not None
    assert large_payload.id is not None

    # The outbound notice must ship the public signed link (usable by external recipients),
    # not the auth-gated internal route that lands them on "Request access to this thread".
    signed_url = signed_attachment_download_url(large_payload.id)
    internal_url = large_payload.download_url
    assert "email_attachments/download?token=" in signed_url

    body_by_type: dict[str, str] = {}
    for part in mime_message.walk():
        # Skip attachment parts — file_N.txt/small.txt are text/plain too and would
        # clobber the actual body parts we want to inspect.
        if part.get("Content-Disposition", "").startswith("attachment"):
            continue
        if part.get_content_type() in ["text/plain", "text/html"]:
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                body_by_type[part.get_content_type()] = payload.decode("utf-8")
    # Both the text and HTML notices ship in this draft; assert on each present body part.
    # Assert on the public link prefix rather than the full signed URL, and confirm the
    # auth-gated internal route is absent.
    assert {"text/plain", "text/html"} <= body_by_type.keys()
    for content_type, body in body_by_type.items():
        assert "email_attachments/download?token=" in body, f"Signed link missing from {content_type} notice"
        assert internal_url not in body, f"Internal URL leaked into {content_type} notice"


@pytest.mark.asyncio
async def test_total_attachment_size_with_download_fallback(client: AppClient):
    superuser = await create_user()
    client.current_user = superuser
    # Test cumulative total size limit (18MB)
    # Create a new email with multiple medium files that exceed total limit
    email_draft = await create_email_draft(
        user_id=superuser.id,
        organization_id=superuser.organization_id,
        subject="Test Total Size Limit",
        body_plain="This email tests total attachment size limits",
        to=["recipient@example.com"],
    )
    email_thread = email_draft.thread
    await Mailbox.sync(email_thread)

    # Upload multiple 3MB files - individually under 5MB but together exceed 18MB
    file_3mb = b"3MB file content" * 200_000  # ~3.2MB each

    for i in range(5):  # 5 * 3.2MB = 16MB (under 18MB total limit)
        file_io = io.BytesIO(file_3mb)
        upload_response = await client.post(
            f"/api/email_threads/{email_thread.id}/draft/attachments",
            files={"files": (f"file_{i}.txt", file_io, "text/plain")},
        )
        assert upload_response.status_code == status.HTTP_200_OK

    # Add one more file to exceed the 18MB limit
    file_io = io.BytesIO(file_3mb)
    upload_response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/attachments",
        files={"files": ("file_5.txt", file_io, "text/plain")},
    )
    assert upload_response.status_code == status.HTTP_200_OK

    # Reload draft with attachments before sending
    email_draft_optional = await email_thread.get_draft()
    assert email_draft_optional is not None
    email_draft = email_draft_optional

    # Set up live document content for validation
    topic = email_draft.live_document_topic
    live_doc = await LiveDocument.for_topic(topic)
    markdown_text = live_doc.get("markdown", type=Text)
    markdown_text.insert(0, email_draft.message.body_plain)
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=live_doc.get_update())

    # Send the email to trigger MIME processing with cumulative size limits
    response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/send",
        json={
            "subject": email_draft.message.subject,
            "to": email_draft.message.to,
            "message_body": email_draft.message.body_plain,
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Reload draft with updated content after sending
    await email_draft.refresh_from_db()
    await email_draft.fetch_related("attachments__file")

    # Verify MIME processing respects total size limit
    mime_string = await EmailMimeBuilder.build_mime_string_from_draft(email_draft)

    # Parse the MIME message to check actual attachment parts
    mime_message = message_from_string(mime_string)

    # Find all attachment parts (excluding inline parts and body parts)
    attachment_parts = []
    for part in mime_message.walk():
        content_disposition = part.get("Content-Disposition", "")
        if content_disposition.startswith("attachment"):
            attachment_parts.append(part)

    # Extract filenames from attachment parts
    included_filenames = []
    for part in attachment_parts:
        content_disposition = part.get("Content-Disposition", "")
        if "filename=" in content_disposition:
            # Extract filename from Content-Disposition header
            filename = content_disposition.split("filename=")[1].strip('"')
            included_filenames.append(filename)

    # Should have some files included but not all due to 18MB total limit
    assert len(included_filenames) > 0  # At least some files should be included
    assert len(included_filenames) < 6  # But not all files should be included

    # Verify that total size of included files is under 18MB
    # Calculate the actual total size of attachments that are included
    total_included_size = 0
    for attachment_part in attachment_parts:
        # Get the actual payload size from the attachment part
        payload = attachment_part.get_payload(decode=True)
        if payload:
            total_included_size += len(payload)

    assert total_included_size <= MAX_TOTAL_ATTACHMENT_SIZE

    # Verify that file_5.txt is excluded due to cumulative size limit
    last_attachment = (
        await EmailAttachment.filter(email_message_id=email_draft.id, file__filename="file_5.txt")
        .prefetch_related("file")
        .first()
    )
    assert last_attachment is not None
    last_attachment_payload = await last_attachment.as_payload()

    # Verify that the download URL is included in the email body for oversized attachment
    assert last_attachment_payload.download_url is not None
    assert last_attachment_payload.id is not None

    # Verify that file_5.txt is NOT in the attachment parts (it should be excluded)
    assert "file_5.txt" not in included_filenames

    # The notice must carry the public signed link, not the auth-gated internal route.
    signed_url = signed_attachment_download_url(last_attachment_payload.id)
    internal_url = last_attachment_payload.download_url
    assert "email_attachments/download?token=" in signed_url

    body_by_type: dict[str, str] = {}
    for part in mime_message.walk():
        # Skip attachment parts — file_N.txt/small.txt are text/plain too and would
        # clobber the actual body parts we want to inspect.
        if part.get("Content-Disposition", "").startswith("attachment"):
            continue
        if part.get_content_type() in ["text/plain", "text/html"]:
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                body_by_type[part.get_content_type()] = payload.decode("utf-8")
    # Assert on the public link prefix rather than the full signed URL, and confirm the
    # auth-gated internal route is absent.
    assert {"text/plain", "text/html"} <= body_by_type.keys()
    for content_type, body in body_by_type.items():
        assert "email_attachments/download?token=" in body, f"Signed link missing from {content_type} notice"
        assert internal_url not in body, f"Internal URL leaked into {content_type} notice"


@pytest.mark.asyncio
async def test_attachment_rendering(client: AppClient, email_client: FakeEmailClient):
    """Test that attachments are rendered correctly in the email body"""
    superuser = await create_user()
    client.current_user = superuser

    # Test inline attachment rendering
    email_message = await create_email_message(
        creator_id=superuser.id,
        organization_id=superuser.organization_id,
        subject="Email with Inline Attachment",
        body_plain="This email has an inline attachment",
        to=[superuser.email],
        body_html="<p>This email has an inline attachment</p><img src='cid:attachment1' alt='Inline Image'>",
    )
    with open("tests/fixtures/image.jpeg", "rb") as f:
        image_content = f.read()
    file_ref = await store_file(content=io.BytesIO(image_content), filename="image.jpeg", content_type="image/jpeg")
    attachment = await EmailAttachment.create(
        email_message_id=email_message.id,
        thread_id=email_message.thread_id,
        file=file_ref,
        content_id="attachment1",
        is_inline=True,
        is_referenced_in_html=True,
    )

    email_thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(email_thread)

    response = await client.get(f"/api/email_threads/{email_message.thread_id}")
    assert response.status_code == status.HTTP_200_OK
    message_id = response.json()["timeline"][0]["message"]["id"]
    # The body lives on the content sub-resource, not the timeline summary.
    content = await client.get(f"/api/email_threads/{email_message.thread_id}/email_messages/{message_id}/content")
    assert content.status_code == status.HTTP_200_OK
    content_body = content.json()
    download_path = f"email_threads/{attachment.thread_id}/attachments/{attachment.id}/download"
    assert download_path in content_body["content_html"]
    assert "cid:attachment1" not in content_body["content_html"]

    # Test out-of-line attachment rendering
    email_message.body_html = "<p>See attached file</p>"
    await email_message.save()

    attachment.is_inline = False
    attachment.is_referenced_in_html = False
    await attachment.save()
    await attachment.fetch_related("file")

    response = await client.get(f"/api/email_threads/{email_message.thread_id}")
    assert response.status_code == status.HTTP_200_OK
    message_id = response.json()["timeline"][0]["message"]["id"]
    content = await client.get(f"/api/email_threads/{email_message.thread_id}/email_messages/{message_id}/content")
    assert content.status_code == status.HTTP_200_OK
    attachment_payload = next(a for a in content.json()["attachments"] if a["id"] == str(attachment.id))
    assert download_path in attachment_payload["download_url"]
    assert attachment_payload["filename"] == attachment.file.filename


@pytest.mark.asyncio
async def test_deleted_inline_attachment_excluded_from_sent_email(client: AppClient, email_client: FakeEmailClient):
    """Test that inline attachments removed from the email body are deleted when sending.

    Scenario:
    1. User creates a draft and uploads an inline image and a regular attachment
    2. User removes the image from the editor (but the EmailAttachment record remains)
    3. User sends the email
    4. The sent email should NOT include the deleted inline image
    5. The deleted inline attachment should be removed from the database
    6. The regular attachment should remain in the database and be sent

    This tests the bug where deleted inline images were still being attached to sent emails
    because the EmailAttachment records were never cleaned up when images were removed from
    the editor.
    """
    user = await create_user(email="test@convictional.com")

    with client.current_user_as(user):
        # Create a draft email
        draft_message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            message_type=EmailMessageType.DRAFT,
            subject="Email with inline image that will be deleted",
            body_plain="",
            to=["recipient@example.com"],
        )
        draft = await EmailDraft.from_message(draft_message)
        thread = await EmailThread.get(id=draft.thread_id)
        await Mailbox.sync(thread)

        # Upload an inline image attachment via the JSON endpoint
        image_content = b"fake image content for inline attachment"

        response = await client.post(
            f"/api/email_threads/{draft.thread_id}/draft/attachments",
            files={"files": ("inline-screenshot.png", io.BytesIO(image_content), "image/png")},
        )
        assert response.status_code == status.HTTP_200_OK

        # Upload a regular (non-inline) attachment
        regular_attachment_content = b"regular attachment content"
        response = await client.post(
            f"/api/email_threads/{draft.thread_id}/draft/attachments",
            files={"files": ("document.pdf", io.BytesIO(regular_attachment_content), "application/pdf")},
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify attachments were created
        await draft_message.refresh_from_db()
        await draft_message.fetch_related("attachments__file")
        assert len(draft_message.attachments) == 2

        inline_attachment = next(a for a in draft_message.attachments if a.is_inline)
        regular_attachment = next(a for a in draft_message.attachments if not a.is_inline)

        assert inline_attachment.is_inline is True
        assert inline_attachment.content_id is not None
        assert regular_attachment.is_inline is False

        # Simulate the user deleting the inline image from the editor
        body_without_image = "<p>I removed the screenshot, here's just text instead.</p>"
        draft_message.body_markdown = body_without_image
        draft_message.body_html = body_without_image
        await draft_message.save()

        await draft_message.refresh_from_db()
        await draft_message.fetch_related("attachments__file")
        draft = await EmailDraft.from_message(draft_message)

        # Test the consolidated attachment filtering logic
        sendable_attachments = draft._get_sendable_attachments()
        inline_sendable = [a for a in sendable_attachments if a.is_inline]
        regular_sendable = [a for a in sendable_attachments if not a.is_inline]

        assert len(inline_sendable) == 0, "Deleted inline attachment should not be sendable"
        assert len(regular_sendable) == 1, "Regular attachment should remain sendable"
        assert regular_sendable[0].id == regular_attachment.id

        await draft.mark_as_sent(
            sent_from=EmailAddress.parse("test@convictional.com"),
            external_message_id="external-123",
            external_thread_id="thread-123",
            external_history_id="history-123",
            message_id="message-123",
            headers=EmailHeaders([]),
            preview="Preview text",
        )

        # Verify only the regular attachment remains in the database
        remaining_attachments = await EmailAttachment.filter(email_message_id=draft.id).all()
        assert len(remaining_attachments) == 1, "Only regular attachment should remain after sending"
        assert remaining_attachments[0].id == regular_attachment.id
        assert not remaining_attachments[0].is_inline


@pytest.mark.asyncio
async def test_attachment_download_denies_users_without_thread_access(client: AppClient):
    owner = await create_user()
    owner_draft = await create_email_draft(
        user_id=owner.id,
        organization_id=owner.organization_id,
        subject="Private thread",
        body_plain="Sensitive",
        to=["recipient@example.com"],
    )

    with client.current_user_as(owner):
        upload_response = await client.post(
            f"/api/email_threads/{owner_draft.thread_id}/draft/attachments",
            files={"files": ("secret.txt", io.BytesIO(b"sensitive"), "text/plain")},
        )
        assert upload_response.status_code == status.HTTP_200_OK

    attachment = await EmailAttachment.first()
    assert attachment is not None

    outsider = await create_user()
    with client.current_user_as(outsider):
        response = await client.get(
            f"/email_threads/{owner_draft.thread_id}/attachments/{attachment.id}/download",
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_public_signed_download_serves_without_thread_access(client: AppClient):
    """The public signed link must serve the file to recipients who have no thread access.

    This is the direct regression test for the reported bug: external recipients (no session)
    and in-app non-collaborators clicked the download link and hit "Request access to this
    email thread" instead of downloading.
    """
    owner = await create_user()
    owner_draft = await create_email_draft(
        user_id=owner.id,
        organization_id=owner.organization_id,
        subject="Thread with oversized attachment",
        body_plain="See the download link",
        to=["recipient@example.com"],
    )

    with client.current_user_as(owner):
        upload_response = await client.post(
            f"/api/email_threads/{owner_draft.thread_id}/draft/attachments",
            files={"files": ("big.txt", io.BytesIO(b"payload"), "text/plain")},
        )
        assert upload_response.status_code == status.HTTP_200_OK

    attachment = await EmailAttachment.first()
    assert attachment is not None
    token = sign_attachment_download_token(attachment.id)

    # Logged-out external recipient (no Convictional session) gets the file, not a request-access redirect.
    with client.logged_out():
        response = await client.get(
            f"/email_attachments/download?token={token}",
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_302_FOUND

    # In-app non-collaborator also succeeds via the signed link.
    outsider = await create_user()
    with client.current_user_as(outsider):
        response = await client.get(
            f"/email_attachments/download?token={token}",
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_302_FOUND


@pytest.mark.asyncio
async def test_public_signed_download_rejects_bad_token(client: AppClient):
    """Invalid, tampered, or dangling (deleted-attachment) tokens 404 rather than redirecting to request-access."""
    owner = await create_user()
    owner_draft = await create_email_draft(
        user_id=owner.id,
        organization_id=owner.organization_id,
        subject="Thread with oversized attachment",
        body_plain="See the download link",
        to=["recipient@example.com"],
    )

    with client.current_user_as(owner):
        upload_response = await client.post(
            f"/api/email_threads/{owner_draft.thread_id}/draft/attachments",
            files={"files": ("big.txt", io.BytesIO(b"payload"), "text/plain")},
        )
        assert upload_response.status_code == status.HTTP_200_OK

    attachment = await EmailAttachment.first()
    assert attachment is not None
    token = sign_attachment_download_token(attachment.id)

    with client.logged_out():
        # Tampered token
        tampered = await client.get(
            f"/email_attachments/download?token={token}x",
            follow_redirects=False,
        )
        assert tampered.status_code == status.HTTP_404_NOT_FOUND

        # Garbage token
        garbage = await client.get(
            "/email_attachments/download?token=not-a-real-token",
            follow_redirects=False,
        )
        assert garbage.status_code == status.HTTP_404_NOT_FOUND

        # Valid token for a now-deleted attachment
        await attachment.delete()
        missing = await client.get(
            f"/email_attachments/download?token={token}",
            follow_redirects=False,
        )
        assert missing.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_unsupported_inline_attachment_visibility(client: AppClient, email_client: FakeEmailClient):
    """Test that inline attachments in unsupported formats appear in attachment list as fallback"""
    user = await create_user()
    client.current_user = user

    email_message = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        subject="Email with HEIC Inline Attachment",
        body_plain="This email has a HEIC inline attachment",
        to=[user.email],
        body_html="<p>Image: <img src='cid:heic-image'></p>",
    )

    heic_file = await store_file(
        content=io.BytesIO(b"fake heic image content"),
        filename="photo.heic",
        content_type="image/heic",
    )
    heic_attachment = await EmailAttachment.create(
        email_message_id=email_message.id,
        thread_id=email_message.thread_id,
        file=heic_file,
        content_id="heic-image",
        is_inline=True,
        is_referenced_in_html=True,
    )

    email_thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(email_thread)

    response = await client.get(f"/api/email_threads/{email_message.thread_id}")
    assert response.status_code == status.HTTP_200_OK

    message_id = response.json()["timeline"][0]["message"]["id"]
    content = await client.get(f"/api/email_threads/{email_message.thread_id}/email_messages/{message_id}/content")
    assert content.status_code == status.HTTP_200_OK
    attachment_payload = next(a for a in content.json()["attachments"] if a["id"] == str(heic_attachment.id))
    download_path = f"email_threads/{heic_attachment.thread_id}/attachments/{heic_attachment.id}/download"
    assert download_path in attachment_payload["download_url"]
    assert attachment_payload["filename"] == "photo.heic"
    assert attachment_payload["show_in_list"] is True


@pytest.mark.asyncio
async def test_non_inline_attachment_link_stripped_from_sent_body(client: AppClient):
    superuser = await create_user()
    client.current_user = superuser

    email_draft = await create_email_draft(
        user_id=superuser.id,
        organization_id=superuser.organization_id,
        subject="Email with dropped attachment link",
        body_plain="See the dropped file below",
        to=["recipient@example.com"],
    )
    email_thread = email_draft.thread
    await Mailbox.sync(email_thread)

    # Normal-sized non-image file dropped into the body -> dead internal download link
    response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/attachments",
        files={"files": ("report.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert response.status_code == status.HTTP_200_OK

    # Image -> classified inline by the image/ content-type prefix, must stay as cid:
    with open("tests/fixtures/image.jpeg", "rb") as f:
        image_content = f.read()
    response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/attachments",
        files={"files": ("image.png", io.BytesIO(image_content), "image/png")},
    )
    assert response.status_code == status.HTTP_200_OK

    # Oversized non-image file -> out-of-scope boundary, keeps its download notice anchor
    response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/attachments",
        files={"files": ("big.pdf", io.BytesIO(b"%PDF-1.4 " + b"x" * (6 * 1024 * 1024)), "application/pdf")},
    )
    assert response.status_code == status.HTTP_200_OK

    await email_draft.refresh_from_db()
    await email_draft.fetch_related("attachments__file")

    attachments = await EmailAttachment.filter(email_message_id=email_draft.id).prefetch_related("file")
    attachment_map = {att.file.filename: att for att in attachments}
    pdf_attachment = attachment_map["report.pdf"]
    png_attachment = attachment_map["image.png"]
    big_attachment = attachment_map["big.pdf"]

    pdf_url = pdf_attachment._download_url()
    png_url = png_attachment._download_url()
    big_url = big_attachment._download_url()
    assert pdf_url is not None
    assert png_url is not None
    assert big_url is not None

    # Entity-encoded content and an unrelated link wrap the stripped anchor so we can
    # assert the surrounding body survives byte-for-byte (no bs4 re-serialization).
    email_draft.message.body_html = (
        "<p>Quote:&nbsp;&ldquo;hi&rdquo;&mdash;done&nbsp;&amp;&nbsp;more</p>"
        f'<p>doc</p><a href="{pdf_url}">report.pdf</a>'
        '<p>See <a href="https://example.com">our site</a> &rsquo;round here.</p>'
        f'<p>img</p><img src="{png_url}" alt="image.png">'
        f'<p>big</p><a href="{big_url}">big.pdf</a>'
    )
    await email_draft.message.save()

    mime_string = await EmailMimeBuilder.build_mime_string_from_draft(email_draft)
    mime_message = message_from_string(mime_string)

    html_body = ""
    attachment_filenames = []
    for part in mime_message.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            assert isinstance(payload, bytes)
            html_body = payload.decode("utf-8")
        content_disposition = part.get("Content-Disposition", "")
        if content_disposition.startswith("attachment") and "filename=" in content_disposition:
            attachment_filenames.append(content_disposition.split("filename=")[1].strip('"'))

    # 1. The dead internal download link for the normal-sized non-image must be gone
    assert pdf_url not in html_body
    # 2. Its path fragment must be gone too
    assert f"attachments/{pdf_attachment.id}/download" not in html_body
    # 3. The filename survives as plain text after the anchor is unwrapped
    assert "report.pdf" in html_body
    # 4. No anchor element still points at the dead url
    assert BeautifulSoup(html_body, "html.parser").find_all("a", href=pdf_url) == []

    # 5. Inline image regression: stays referenced by cid:, never by the internal url
    assert f"cid:{png_attachment.content_id}" in html_body
    assert png_url not in html_body

    # 6. The normal-sized non-image still ships as a real attachment part
    assert "report.pdf" in attachment_filenames

    # 7. Out-of-scope boundary: the oversized-notice download anchor must NOT be unwrapped
    assert big_url in html_body
    assert BeautifulSoup(html_body, "html.parser").find_all("a", href=big_url) != []

    # 8. Byte-fidelity: entity-encoded content around the stripped anchor survives verbatim
    # (no decoding to \xa0, smart quotes, em dash, etc.) and the literal &amp; is untouched.
    assert "&nbsp;&ldquo;hi&rdquo;&mdash;done&nbsp;&amp;&nbsp;" in html_body
    assert "&rsquo;round here." in html_body
    assert "\xa0" not in html_body
    assert "“" not in html_body and "”" not in html_body
    assert "—" not in html_body

    # 9. An unrelated link in the body is left completely untouched
    assert '<a href="https://example.com">our site</a>' in html_body


@pytest.mark.asyncio
async def test_outgoing_html_wrapped_in_pre_wrap(client: AppClient):
    user = await create_user()
    client.current_user = user

    email_draft = await create_email_draft(
        user_id=user.id,
        organization_id=user.organization_id,
        subject="Whitespace fidelity",
        body_plain="hello",
        to=["recipient@example.com"],
    )
    await Mailbox.sync(email_draft.thread)

    authored_html = "<div>a   b</div><div><br></div>"
    email_draft.message.body_html = authored_html
    await email_draft.message.save()

    mime_string = await EmailMimeBuilder.build_mime_string_from_draft(email_draft)
    mime_message = message_from_string(mime_string)

    html_body = ""
    for part in mime_message.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            assert isinstance(payload, bytes)
            html_body = payload.decode("utf-8")

    # External clients don't load our email.css, so authored whitespace fidelity rides on an
    # inline white-space: pre-wrap wrapper around the whole HTML body (best-effort).
    assert html_body.startswith('<div style="white-space: pre-wrap;">')
    assert html_body.endswith("</div>")
    # The authored body stays whitespace-tight inside the wrapper.
    assert authored_html in html_body
