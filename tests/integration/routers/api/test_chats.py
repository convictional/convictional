from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin
from uuid import UUID, uuid4

import pytest
from fastapi import status

from app.jobs.mailbox import SyncMailboxJob
from app.jobs.notifications import SendEventEmailJob, SendMentionJob
from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.collaboration.workspace import Attachment, Collaborator, Event, LinkPreview, Mention, Visit
from app.models.workspaces.chat import Chat, ChatMessage
from app.routers.api.chats import CHAT_AROUND_CONTEXT
from config.enums import EventAction, LinkPreviewStatus, LinkPreviewType
from config.settings import settings
from infra.db import GlobalID
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_chat,
    create_chat_message,
    create_collaborator,
    create_group,
    create_group_member,
    create_organization,
    create_user,
)


@pytest.mark.asyncio
async def test_find_or_create_direct_chat(client: AppClient):
    user = await create_user(email="dm-panel@convictional.com")
    recipient = await create_user(name="Alice", organization_id=user.organization_id)

    with client.current_user_as(user):
        # Creates a new DM chat
        response = await client.post("/api/chats", json={"recipient_ids": [str(recipient.id)]})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["chat_id"]
        assert data["workspace_id"]
        assert data["recipient"]["display_name"] == "Alice"
        chat_id = data["chat_id"]

        # Calling again returns the same chat
        response = await client.post("/api/chats", json={"recipient_ids": [str(recipient.id)]})
        assert response.json()["chat_id"] == chat_id


@pytest.mark.asyncio
async def test_find_or_create_self_chat(client: AppClient):
    user = await create_user(email="self-chat@convictional.com")

    with client.current_user_as(user):
        response = await client.post("/api/chats", json={"recipient_ids": [str(user.id)]})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["type"] == "self"
        assert data["name"] == "Note to self"

        # Dedupe — returns the same chat
        response2 = await client.post("/api/chats", json={"recipient_ids": [str(user.id)]})
        assert response2.json()["chat_id"] == data["chat_id"]


@pytest.mark.asyncio
async def test_find_or_create_direct_chat_errors(client: AppClient):
    user = await create_user(email="dm-err@convictional.com")
    other_org_user = await create_user()
    other = await create_user(organization_id=user.organization_id)

    with client.current_user_as(user):
        # Self mixed with others is rejected
        response = await client.post("/api/chats", json={"recipient_ids": [str(user.id), str(other.id)]})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # Recipient not found
        response = await client.post("/api/chats", json={"recipient_ids": [str(uuid4())]})
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Recipient in different org
        response = await client.post("/api/chats", json={"recipient_ids": [str(other_org_user.id)]})
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_chat_detail(client: AppClient):
    user = await create_user(email="chat-detail@convictional.com")
    recipient = await create_user(name="DetailRecip", organization_id=user.organization_id)
    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)

    with client.current_user_as(user):
        # DM chat returns recipient name as title
        response = await client.get(f"/api/chats/{chat.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["chat_id"] == str(chat.id)
        assert data["workspace_id"] == str(chat.workspace_id)
        assert data["chat_title"] == "DetailRecip"
        assert data["is_group_chat"] is False
        # The React chat header renders display_name + picture per member,
        # so the contract is the full user shape — not just ids.
        members_by_user_id = {m["user"]["id"]: m for m in data["collaborators"]}
        assert set(members_by_user_id) == {str(user.id), str(recipient.id)}
        recipient_user = members_by_user_id[str(recipient.id)]["user"]
        assert recipient_user["display_name"] == recipient.display_name
        assert "picture" in recipient_user

    # Non-member gets 404
    other_user = await create_user(organization_id=user.organization_id)
    with client.current_user_as(other_user):
        response = await client.get(f"/api/chats/{chat.id}")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_chat_detail_mailbox_state(client: AppClient):
    user = await create_user(email="chat-detail-mailbox@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    with client.current_user_as(user):
        # No mailbox entry yet — `mailbox` is null
        response = await client.get(f"/api/chats/{chat.id}")
        assert response.json()["mailbox"] is None

    # Create a message so Mailbox.sync produces an unread inbox entry for the user
    await create_chat_message(chat_id=chat.id, user_id=other.id, content="Hi")
    await chat.refresh_from_db()
    await Mailbox.sync(chat)

    with client.current_user_as(user):
        response = await client.get(f"/api/chats/{chat.id}")
        mailbox = response.json()["mailbox"]
        entry = await MailboxEntry.get(owner_id=user.id, resource_gid=str(GlobalID.create("Chat", chat.id)))
        assert mailbox["id"] == str(entry.id)
        assert mailbox["is_unread"] is True
        assert mailbox["is_archived"] is False
        assert mailbox["is_snoozed"] is False
        assert mailbox["snoozed_until"] is None

        # Snooze and re-check that the snoozed fields surface
        snoozed_until = datetime.now(UTC) + timedelta(hours=1)
        await Mailbox(user=user).snooze(chat, snoozed_until)

        response = await client.get(f"/api/chats/{chat.id}")
        mailbox = response.json()["mailbox"]
        assert mailbox["is_snoozed"] is True
        assert mailbox["snoozed_until"] is not None

        # Expired snooze reads as not snoozed even before the recurring
        # unsnooze sweep runs — matches MailboxEntryFilters.is_snoozed().
        entry.snoozed_until = datetime.now(UTC) - timedelta(minutes=1)
        await entry.save(update_fields=["snoozed_until"])

        response = await client.get(f"/api/chats/{chat.id}")
        mailbox = response.json()["mailbox"]
        assert mailbox["is_snoozed"] is False
        assert mailbox["snoozed_until"] is not None


@pytest.mark.asyncio
async def test_chat_detail_group(client: AppClient):
    user = await create_user(email="chat-detail-group@convictional.com")
    group = await create_group(name="Test Group", organization_id=user.organization_id)
    await create_group_member(group_id=group.id, user_id=user.id)
    chat = await create_chat(organization_id=user.organization_id, group_id=group.id, title="Test Group")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    with client.current_user_as(user):
        response = await client.get(f"/api/chats/{chat.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["chat_title"] == "Test Group"
        assert data["is_group_chat"] is True
        assert {m["user"]["id"] for m in data["collaborators"]} == {str(user.id)}
        member = data["collaborators"][0]["user"]
        assert member["display_name"] == user.display_name
        assert "picture" in member


@pytest.mark.asyncio
async def test_list_chat_messages(client: AppClient):
    user = await create_user(email="dm-list@convictional.com")
    recipient = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)

    for i in range(3):
        await create_chat_message(chat_id=chat.id, user_id=recipient.id, content=f"Message {i}")

    with client.current_user_as(user):
        response = await client.get(f"/api/chats/{chat.id}/messages")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["messages"]) == 3
        assert all(m["content"] for m in data["messages"])

    # Non-member cannot access
    outsider = await create_user(email="outsider@convictional.com")
    with client.current_user_as(outsider):
        response = await client.get(f"/api/chats/{chat.id}/messages")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_list_chat_messages_pagination(client: AppClient):
    per_page = 50
    user = await create_user(email="dm-page@convictional.com")
    recipient = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)

    base_time = datetime(2025, 1, 1, tzinfo=UTC)
    total_messages = per_page + 5
    for i in range(total_messages):
        await create_chat_message(
            chat_id=chat.id,
            user_id=recipient.id,
            content=f"Message {i}",
            created_at=base_time + timedelta(seconds=i),
        )

    with client.current_user_as(user):
        response = await client.get(f"/api/chats/{chat.id}/messages")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["messages"]) == per_page
        assert data["has_more"] is True
        assert data["next_cursor"] is not None
        # Messages are in chronological order (oldest first within the page)
        contents = [m["content"] for m in data["messages"]]
        assert f"Message {total_messages - 1}" in contents
        assert "Message 0" not in contents

        # Second page via cursor
        response = await client.get(f"/api/chats/{chat.id}/messages?cursor={data['next_cursor']}")
        assert response.status_code == status.HTTP_200_OK
        page2 = response.json()
        assert len(page2["messages"]) == 5
        assert page2["has_more"] is False


@pytest.mark.asyncio
async def test_list_chat_messages_forward_pagination(client: AppClient):
    per_page = 50
    user = await create_user(email="dm-forward@convictional.com")
    recipient = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)

    base_time = datetime(2025, 1, 1, tzinfo=UTC)
    total_messages = per_page + 5
    messages = [
        await create_chat_message(
            chat_id=chat.id,
            user_id=recipient.id,
            content=f"Message {i}",
            created_at=base_time + timedelta(seconds=i),
        )
        for i in range(total_messages)
    ]

    with client.current_user_as(user):
        # direction=newer&after=<anchor> seeds the forward walk: the page holds
        # the messages strictly newer than the anchor, oldest-first, and fills to
        # per_page with more newer history remaining.
        anchor = messages[0]
        response = await client.get(f"/api/chats/{chat.id}/messages?direction=newer&after={anchor.id}")
        assert response.status_code == status.HTTP_200_OK
        page1 = response.json()
        page1_ids = [m["id"] for m in page1["messages"]]
        assert len(page1_ids) == per_page
        assert page1_ids == [str(messages[i].id) for i in range(1, 1 + per_page)]
        assert str(anchor.id) not in page1_ids
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        # Subsequent forward pages ride the opaque next_cursor (after is dropped).
        response = await client.get(f"/api/chats/{chat.id}/messages?direction=newer&cursor={page1['next_cursor']}")
        assert response.status_code == status.HTTP_200_OK
        page2 = response.json()
        page2_ids = [m["id"] for m in page2["messages"]]
        assert page2_ids == [str(messages[i].id) for i in range(1 + per_page, total_messages)]
        # Reached the live tail: last forward page has no more newer history.
        assert page2["has_more"] is False
        assert page2_ids[-1] == str(messages[-1].id)

        # after pointing at the newest message → already at the tail, empty page.
        response = await client.get(f"/api/chats/{chat.id}/messages?direction=newer&after={messages[-1].id}")
        tail = response.json()
        assert tail["messages"] == []
        assert tail["has_more"] is False

        # Unknown / deleted / foreign anchors 404, matching the around endpoint.
        deleted = messages[2]
        await deleted.soft_delete()
        assert (
            await client.get(f"/api/chats/{chat.id}/messages?direction=newer&after={deleted.id}")
        ).status_code == status.HTTP_404_NOT_FOUND
        assert (
            await client.get(f"/api/chats/{chat.id}/messages?direction=newer&after={uuid4()}")
        ).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_chat_messages_around(client: AppClient):
    context = CHAT_AROUND_CONTEXT
    user = await create_user(email="dm-around@convictional.com")
    recipient = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)

    base_time = datetime(2025, 1, 1, tzinfo=UTC)
    total_messages = 120
    messages = [
        await create_chat_message(
            chat_id=chat.id,
            user_id=recipient.id,
            content=f"Message {i}",
            created_at=base_time + timedelta(seconds=i),
        )
        for i in range(total_messages)
    ]

    with client.current_user_as(user):
        # Anchor in the middle → full symmetric window, centered, ASC, more history below.
        middle = messages[60]
        response = await client.get(f"/api/chats/{chat.id}/messages/around/{middle.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        window = data["messages"]
        assert len(window) == 2 * context + 1
        assert data["at_tail"] is False
        assert data["has_more"] is True
        assert data["next_cursor"] is not None
        ids = [m["id"] for m in window]
        assert ids[context] == str(middle.id)
        # Strictly ascending by created_at across the whole window.
        timestamps = [m["created_at"] for m in window]
        assert timestamps == sorted(timestamps)
        assert ids == [str(messages[i].id) for i in range(60 - context, 60 + context + 1)]

        # Cursor-compat: the window's next_cursor is a valid loadMore cursor that
        # walks strictly older with no overlap or gap against the window's oldest.
        oldest_in_window = window[0]
        response = await client.get(f"/api/chats/{chat.id}/messages?cursor={data['next_cursor']}")
        assert response.status_code == status.HTTP_200_OK
        older_page = response.json()["messages"]
        assert all(m["created_at"] < oldest_in_window["created_at"] for m in older_page)
        assert {m["id"] for m in older_page}.isdisjoint({m["id"] for m in window})
        # No gap: the newest of the older page is the message immediately before the window.
        assert older_page[-1]["id"] == str(messages[60 - context - 1].id)

        # Anchor at the oldest message → no more history below.
        response = await client.get(f"/api/chats/{chat.id}/messages/around/{messages[0].id}")
        oldest_data = response.json()
        assert oldest_data["messages"][0]["id"] == str(messages[0].id)
        assert oldest_data["has_more"] is False
        assert oldest_data["next_cursor"] is None

        # Anchor at the newest message → live tail is loaded.
        response = await client.get(f"/api/chats/{chat.id}/messages/around/{messages[-1].id}")
        newest_data = response.json()
        assert newest_data["at_tail"] is True
        assert newest_data["messages"][-1]["id"] == str(messages[-1].id)

        # 404s: deleted anchor, unknown id, and an anchor that lives in another chat.
        deleted = messages[30]
        await deleted.soft_delete()
        assert (await client.get(f"/api/chats/{chat.id}/messages/around/{deleted.id}")).status_code == (
            status.HTTP_404_NOT_FOUND
        )
        assert (await client.get(f"/api/chats/{chat.id}/messages/around/{uuid4()}")).status_code == (
            status.HTTP_404_NOT_FOUND
        )

        other_chat = await create_chat(organization_id=user.organization_id)
        await create_collaborator(workspace_id=other_chat.workspace_id, user_id=user.id)
        foreign = await create_chat_message(chat_id=other_chat.id, user_id=user.id, content="elsewhere")
        assert (await client.get(f"/api/chats/{chat.id}/messages/around/{foreign.id}")).status_code == (
            status.HTTP_404_NOT_FOUND
        )

    # Non-member gets 404 (chat access fails before anchor lookup), whether they're
    # in another org or a same-org user who simply isn't a collaborator on this chat.
    outsider = await create_user(email="around-outsider@convictional.com")
    same_org_non_collaborator = await create_user(organization_id=user.organization_id)
    for non_member in (outsider, same_org_non_collaborator):
        with client.current_user_as(non_member):
            response = await client.get(f"/api/chats/{chat.id}/messages/around/{messages[60].id}")
            assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_send_chat_message(client: AppClient, background_jobs: InlineJobs):
    user = await create_user(email="dm-send@convictional.com")
    recipient = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)
    # Production subscribes via Chat.upsert_collaborators; create_collaborator bypasses it.
    await chat.workspace.subscribe(recipient.id)

    background_jobs.reset()

    with client.current_user_as(user):
        # Plain text message persists content and has no link preview
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "Hello from panel!"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["message"]["content"] == "Hello from panel!"
        assert data["message"]["user"]["id"] == str(user.id)
        assert data["message"]["link_preview"] is None

        # IN_APP fan-out: one SyncMailboxJob per event refreshes every collaborator's
        # row (including sender). No email jobs for chat. ChatMailboxEntry decides each
        # row's labels — sender stays out of inbox, recipients land in inbox+unread.
        sync_jobs = background_jobs.all_completed_jobs_by_type(SyncMailboxJob)
        assert len(sync_jobs) == 1
        assert not background_jobs.has_completed_job(SendEventEmailJob)

        sender_entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=user.id)
        assert sender_entry is not None
        assert sender_entry.last_comment == "Hello from panel!"
        assert not sender_entry.is_inbox
        assert not sender_entry.is_unread

        recipient_entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=recipient.id)
        assert recipient_entry is not None
        assert recipient_entry.last_comment == "Hello from panel!"
        assert recipient_entry.is_inbox
        assert recipient_entry.is_unread

        # Raw markdown ships on the wire; the React client renders it.
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "**bold**"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["message"]["content"] == "**bold**"

        # Messages persisted
        messages = await ChatMessage.filter(chat_id=chat.id).all()
        assert len(messages) == 2
        assert {m.content for m in messages} == {"Hello from panel!", "**bold**"}

        # Each message emits a CHAT_MESSAGE_CREATED event on the chat's workspace
        created_events = await Event.filter(
            workspace_id=chat.workspace_id, action=EventAction.CHAT_MESSAGE_CREATED
        ).all()
        assert len(created_events) == 2
        assert all(e.creator_id == user.id for e in created_events)

        # Mailbox entry created for recipient as unread inbox item
        entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=recipient.id)
        assert entry is not None
        assert entry.is_inbox
        assert entry.is_unread

        # Blank content rejected
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "   "},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # Empty content rejected
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": ""},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_send_chat_message_with_attachment(client: AppClient):
    user = await create_user(email="dm-attach@convictional.com")
    recipient = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)

    claim_id = uuid4()
    attachment = await create_attachment(
        user_id=user.id,
        workspace_id=None,
        claim_id=claim_id,
        comment_gid=None,
        filename="report.csv",
    )
    # The composer embeds the uploaded file as a body link, so the saved content references it.
    download_url = urljoin(str(settings.base_url), f"/workspaces/attachments/{attachment.id}/download")
    content = f"Here is the file [report.csv]({download_url})"

    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={
                "content": content,
                "attachment_claim_id": str(claim_id),
                "skip_link_preview": True,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["message"]["content"] == content

        # Attachment was claimed: claim_id cleared and comment_gid set to the message
        await attachment.refresh_from_db()
        assert attachment.claim_id is None
        message = await ChatMessage.filter(chat_id=chat.id).first()
        assert message is not None
        assert attachment.comment_gid == message.global_id

    # Sending with a claim_id that has no matching attachments still succeeds
    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={
                "content": "No attachments here",
                "attachment_claim_id": str(uuid4()),
                "skip_link_preview": True,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.asyncio
async def test_send_chat_message_drops_unreferenced_attachment(client: AppClient):
    # A file removed from the draft before sending (its link no longer in the content) must not
    # persist as an attachment card. cleanup_unreferenced_attachments deletes non-image files
    # that the saved content doesn't reference, mirroring the existing inline-image rule.
    user = await create_user(email="dm-drop-attach@convictional.com")
    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    claim_id = uuid4()
    attachment = await create_attachment(
        user_id=user.id,
        workspace_id=None,
        claim_id=claim_id,
        comment_gid=None,
        filename="orphan.csv",
    )

    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={
                "content": "Changed my mind, no file",
                "attachment_claim_id": str(claim_id),
                "skip_link_preview": True,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    assert await Attachment.filter(id=attachment.id).exists() is False


@pytest.mark.asyncio
async def test_chat_messages_serialize_enriched_file_previews(client: AppClient):
    # File cards are exposed only through the link preview — there is no separate attachments
    # list. A pasted or uploaded attachment link persists just the filename (in title), so its
    # content type and size are re-resolved at serialize time.
    user = await create_user(email="dm-files@convictional.com")
    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    doc_content = b"a,b\n1,2\n"
    doc = await create_attachment(
        user_id=user.id,
        workspace_id=chat.workspace_id,
        filename="report.csv",
        content_type="text/csv",
        content=doc_content,
    )
    url = urljoin(str(settings.base_url), f"/workspaces/attachments/{doc.id}/download")
    preview = await LinkPreview.upsert(
        url,
        {
            "status": LinkPreviewStatus.READY,
            "type": LinkPreviewType.LINK,
            "title": "report.csv",
            "description": None,
            "image_url": None,
            "site_name": None,
            "oembed_html": None,
        },
    )
    message = await create_chat_message(
        chat_id=chat.id, user_id=user.id, content=f"[report.csv]({url})", link_preview_id=preview.id
    )

    with client.current_user_as(user):
        response = await client.get(f"/api/chats/{chat.id}/messages")
    assert response.status_code == status.HTTP_200_OK
    [serialized] = response.json()["messages"]

    assert "attachments" not in serialized
    assert serialized["id"] == str(message.id)
    link_preview_data = serialized["link_preview"]
    assert link_preview_data["resource_kind"] == "file"
    assert link_preview_data["file"] == {
        "file_name": "report.csv",
        "content_type": "text/csv",
        "byte_size": len(doc_content),
    }


@pytest.mark.asyncio
async def test_send_chat_message_with_link_preview(client: AppClient):
    user = await create_user(email="dm-lp@convictional.com")
    recipient = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)

    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "Check out https://github.com/anthropics/claude-code"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        message = response.json()["message"]
        assert message["link_preview"] is not None
        assert message["link_preview"]["domain"] == "github.com"

        # Verify association persisted
        db_message = await ChatMessage.get(id=message["id"]).prefetch_related("link_preview")
        assert db_message.link_preview_id is not None


@pytest.mark.asyncio
async def test_response_includes_edited_at_and_reactions(client: AppClient):
    user = await create_user(email="dm-fields@convictional.com")
    recipient = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)

    with client.current_user_as(user):
        # New message has null edited_at and empty reactions
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "Hello"},
        )
        msg = response.json()["message"]
        assert msg["edited_at"] is None
        assert msg["reactions"] == {}

        # After edit, edited_at is populated (was_edited requires >10s gap)
        message_id = msg["id"]
        db_msg = await ChatMessage.get(id=message_id)
        db_msg.created_at = db_msg.created_at - timedelta(seconds=30)
        await db_msg.save(update_fields=["created_at"])

        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message_id}",
            json={"content": "Hello edited"},
        )
        assert response.status_code == status.HTTP_200_OK
        msg = response.json()["message"]
        assert msg["content"] == "Hello edited"
        assert msg["edited_at"] is not None

        # Inbox endpoint also includes the new fields
        response = await client.get(f"/api/chats/{chat.id}/messages")
        listed = response.json()["messages"][0]
        assert "edited_at" in listed
        assert "reactions" in listed


@pytest.mark.asyncio
async def test_message_mutations_keep_mailbox_entries_current(client: AppClient):
    # Regression: previously, mailbox entries lagged behind the latest chat message
    # because the sender's entry was never materialized (Notifier excluded them) and
    # recipients relied on a per-user async job. The Notifier now enqueues one
    # SyncMailboxJob per event that refreshes every collaborator's row — the
    # per-resource entry class (ChatMailboxEntry) decides each user's labels (sender stays read,
    # recipients land in inbox+unread).
    user = await create_user(email="dm-fresh-mailbox@convictional.com")
    # Pin the recipient's email so the VCR cassette (which records the indexer's
    # embedding request, including both collaborators' emails in the chat title)
    # stays reproducible across test runs that have different factory counters.
    recipient = await create_user(email="dm-fresh-recipient@convictional.com", organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)
    await chat.workspace.subscribe(recipient.id)

    with client.current_user_as(user):
        # Create: both sides see the new message immediately.
        first = await client.post(f"/api/chats/{chat.id}/messages", json={"content": "First"})
        assert first.status_code == status.HTTP_201_CREATED

        sender_entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user.id)
        recipient_entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=recipient.id)
        assert sender_entry.last_comment == "First"
        assert recipient_entry.last_comment == "First"
        assert recipient_entry.is_inbox
        assert recipient_entry.is_unread

        # Edit: the edited content propagates to both mailbox entries.
        message_id = first.json()["message"]["id"]
        edit = await client.patch(
            f"/api/chats/{chat.id}/messages/{message_id}",
            json={"content": "First (edited)"},
        )
        assert edit.status_code == status.HTTP_200_OK

        await sender_entry.refresh_from_db()
        await recipient_entry.refresh_from_db()
        assert sender_entry.last_comment == "First (edited)"
        assert recipient_entry.last_comment == "First (edited)"

        # Send a second message, then delete it: mailbox rolls back to the first.
        second = await client.post(f"/api/chats/{chat.id}/messages", json={"content": "Second"})
        assert second.status_code == status.HTTP_201_CREATED
        await sender_entry.refresh_from_db()
        assert sender_entry.last_comment == "Second"

        deletion = await client.delete(f"/api/chats/{chat.id}/messages/{second.json()['message']['id']}")
        assert deletion.status_code == status.HTTP_204_NO_CONTENT

        await sender_entry.refresh_from_db()
        await recipient_entry.refresh_from_db()
        assert sender_entry.last_comment == "First (edited)"
        assert recipient_entry.last_comment == "First (edited)"


@pytest.mark.asyncio
async def test_edit_chat_message(client: AppClient):
    user = await create_user(email="dm-edit@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    message = await create_chat_message(chat_id=chat.id, user_id=user.id, content="Original")

    with client.current_user_as(user):
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message.id}",
            json={"content": "Updated content"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"]["content"] == "Updated content"

        # Verify persisted
        await message.refresh_from_db()
        assert message.content == "Updated content"

        # Edit emits a CHAT_MESSAGE_EDITED event tied to the acting user
        edited_event = await Event.filter(
            workspace_id=chat.workspace_id, action=EventAction.CHAT_MESSAGE_EDITED
        ).first()
        assert edited_event is not None
        assert edited_event.creator_id == user.id
        assert edited_event.recordable_id == message.id

    # Non-owner gets 403
    with client.current_user_as(other):
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message.id}",
            json={"content": "Hijack attempt"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # Non-member gets 404
    outsider = await create_user(email="outsider-edit@convictional.com")
    with client.current_user_as(outsider):
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message.id}",
            json={"content": "x"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_edit_chat_message_preserves_existing_inline_attachments(client: AppClient):
    # Editing with a fresh claim_id that has no associated uploads must not
    # trigger cleanup of existing inline attachments on the message. The
    # ProseMirror serialize/parse round trip can shift inline image URLs in
    # ways that don't match `attachments/{id}`, so a blind cleanup would
    # incorrectly delete in-use images.
    user = await create_user(email="dm-edit-attach@convictional.com")
    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    message = await create_chat_message(chat_id=chat.id, user_id=user.id, content="Original")
    inline_attachment = await create_attachment(
        user_id=user.id,
        workspace_id=chat.workspace_id,
        claim_id=None,
        comment_gid=message.global_id,
        filename="inline.png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\n",
    )

    with client.current_user_as(user):
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message.id}",
            json={
                "content": "Edited content without the original image URL",
                "attachment_claim_id": str(uuid4()),
            },
        )
        assert response.status_code == status.HTTP_200_OK

    # The existing inline attachment is preserved because no new attachments
    # were claimed for this edit.
    assert await Attachment.filter(id=inline_attachment.id).exists()


@pytest.mark.asyncio
async def test_edit_chat_message_preserves_existing_inline_attachments_when_uploading_new(
    client: AppClient,
):
    # When edit *also* uploads a new attachment, URL-based cleanup runs and would
    # delete existing inline images whose URLs don't survive the ProseMirror
    # serialize/parse round trip. `retained_attachment_ids` lets the editor tell
    # the backend which existing attachments to keep regardless of URL shape.
    user = await create_user(email="dm-edit-attach-mixed@convictional.com")
    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    message = await create_chat_message(chat_id=chat.id, user_id=user.id, content="Original")
    existing_attachment = await create_attachment(
        user_id=user.id,
        workspace_id=chat.workspace_id,
        claim_id=None,
        comment_gid=message.global_id,
        filename="existing.png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\n",
    )

    # Simulate a new attachment being uploaded during this edit session.
    claim_id = uuid4()
    await create_attachment(
        user_id=user.id,
        workspace_id=chat.workspace_id,
        claim_id=claim_id,
        comment_gid=None,
        filename="new.png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\n",
    )

    # Edit content does not reference the existing attachment's URL — mimicking
    # a ProseMirror round trip where the original URL was mangled, or a user
    # who removed the inline image but kept the message and added a new one.
    with client.current_user_as(user):
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message.id}",
            json={
                "content": "Edited content with no original URL",
                "attachment_claim_id": str(claim_id),
                "retained_attachment_ids": [str(existing_attachment.id)],
            },
        )
        assert response.status_code == status.HTTP_200_OK

    # The existing inline attachment must survive even though a new attachment
    # was claimed in the same edit.
    assert await Attachment.filter(id=existing_attachment.id).exists()


@pytest.mark.asyncio
async def test_delete_chat_message(client: AppClient):
    user = await create_user(email="dm-del@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    message = await create_chat_message(chat_id=chat.id, user_id=user.id, content="Delete me")

    # Non-owner gets 403
    with client.current_user_as(other):
        response = await client.delete(f"/api/chats/{chat.id}/messages/{message.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # Owner can delete
    with client.current_user_as(user):
        response = await client.delete(f"/api/chats/{chat.id}/messages/{message.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Message is soft-deleted
        await message.refresh_from_db()
        assert message.deleted_at is not None

        # Delete emits a CHAT_MESSAGE_DELETED event
        deleted_event = await Event.filter(
            workspace_id=chat.workspace_id, action=EventAction.CHAT_MESSAGE_DELETED
        ).first()
        assert deleted_event is not None
        assert deleted_event.creator_id == user.id
        assert deleted_event.recordable_id == message.id

    # Non-member gets 404
    outsider = await create_user(email="outsider-del@convictional.com")
    with client.current_user_as(outsider):
        response = await client.delete(f"/api/chats/{chat.id}/messages/{message.id}")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_toggle_chat_message_reaction(client: AppClient):
    user = await create_user(email="dm-react@convictional.com")
    recipient = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=recipient.id)

    message = await create_chat_message(chat_id=chat.id, user_id=recipient.id, content="React to this")

    with client.current_user_as(user):
        # Add reaction
        response = await client.post(
            f"/api/chats/{chat.id}/messages/{message.id}/reactions?reaction_type=thumbs_up",
        )
        assert response.status_code == status.HTTP_200_OK
        msg = response.json()["message"]
        reaction_user_ids = [r["id"] for r in msg["reactions"]["thumbs_up"]]
        assert str(user.id) in reaction_user_ids

        # Toggle off
        response = await client.post(
            f"/api/chats/{chat.id}/messages/{message.id}/reactions?reaction_type=thumbs_up",
        )
        assert response.status_code == status.HTTP_200_OK
        msg = response.json()["message"]
        assert msg["reactions"].get("thumbs_up", []) == []

    # Non-member gets 404
    outsider = await create_user(email="outsider-react@convictional.com")
    with client.current_user_as(outsider):
        response = await client.post(
            f"/api/chats/{chat.id}/messages/{message.id}/reactions?reaction_type=thumbs_up",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_chats_index(client: AppClient):
    user = await create_user(email="idx@convictional.com")
    other = await create_user(name="Other", organization_id=user.organization_id)

    chat1 = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat1.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat1.workspace_id, user_id=other.id)
    await create_chat_message(chat_id=chat1.id, user_id=other.id, content="Older msg")

    chat2 = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=other.id)
    await create_chat_message(chat_id=chat2.id, user_id=other.id, content="Newer msg")

    with client.current_user_as(user):
        response = await client.get("/api/chats")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["chats"]) == 2
        assert data["chats"][0]["id"] == str(chat2.id)
        assert data["chats"][1]["id"] == str(chat1.id)

        first = data["chats"][0]
        assert first["type"] == "dm"
        assert first["name"] == "Other"
        assert first["latest_message"]["content"] == "Newer msg"
        assert first["latest_message"]["user"]["display_name"] == "Other"
        assert first["user"]["display_name"] == "Other"
        assert first["collaborator_count"] == 2


@pytest.mark.asyncio
async def test_chats_index_excludes_chats_without_messages(client: AppClient):
    user = await create_user(email="idx-empty@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat_with_msg = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat_with_msg.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat_with_msg.workspace_id, user_id=other.id)
    await create_chat_message(chat_id=chat_with_msg.id, user_id=other.id, content="Hello")

    chat_empty = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat_empty.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat_empty.workspace_id, user_id=other.id)

    with client.current_user_as(user):
        response = await client.get("/api/chats")
        data = response.json()
        assert len(data["chats"]) == 1
        assert data["chats"][0]["id"] == str(chat_with_msg.id)


@pytest.mark.asyncio
async def test_chats_index_includes_group_chats(client: AppClient):
    user = await create_user(email="idx-group@convictional.com")
    group = await create_group(name="Team Chat", organization_id=user.organization_id)
    await create_group_member(group_id=group.id, user_id=user.id)

    chat = await create_chat(organization_id=user.organization_id, group_id=group.id, title="Team Chat")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_chat_message(chat_id=chat.id, user_id=user.id, content="Group msg")

    with client.current_user_as(user):
        response = await client.get("/api/chats")
        data = response.json()
        assert len(data["chats"]) == 1
        item = data["chats"][0]
        assert item["type"] == "group"
        assert item["name"] == "Team Chat"
        assert item["collaborator_count"] == 1
        assert item["user"] is None


@pytest.mark.asyncio
async def test_chats_contacts_returns_users_and_groups_without_chats(client: AppClient):
    user = await create_user(email="contacts@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    await create_user(name="Bob", organization_id=user.organization_id)

    # Alice has an active DM chat with user
    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_chat_message(chat_id=chat.id, user_id=alice.id, content="Hi")

    # Group with active chat
    group_with_chat = await create_group(name="Active Group", organization_id=user.organization_id)
    await create_group_member(group_id=group_with_chat.id, user_id=user.id)
    group_chat = await create_chat(
        organization_id=user.organization_id, group_id=group_with_chat.id, name="Active Group"
    )
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=user.id)
    await create_chat_message(chat_id=group_chat.id, user_id=user.id, content="Hey")

    # Group without active chat
    group_no_chat = await create_group(name="Idle Group", organization_id=user.organization_id)
    await create_group_member(group_id=group_no_chat.id, user_id=user.id)
    active_member = await create_user(organization_id=user.organization_id)
    await create_group_member(group_id=group_no_chat.id, user_id=active_member.id)
    deactivated = await create_user(organization_id=user.organization_id)
    await create_group_member(group_id=group_no_chat.id, user_id=deactivated.id)
    await deactivated.soft_delete()

    with client.current_user_as(user):
        response = await client.get("/api/chats/contacts")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        names = [c["name"] for c in data["contacts"]]
        # Bob (no chat) and Idle Group (no chat) should be in contacts, sorted alphabetically
        assert "Bob" in names
        assert "Idle Group" in names
        # Alice and Active Group have active chats, should NOT be in contacts
        assert "Alice" not in names
        assert "Active Group" not in names

        idle_group = next(c for c in data["contacts"] if c["name"] == "Idle Group" and c["type"] == "group")
        assert idle_group["collaborator_count"] == 2


@pytest.mark.asyncio
async def test_create_chat_with_group_id(client: AppClient):
    user = await create_user(email="create-grp@convictional.com")
    group = await create_group(name="Dev Team", organization_id=user.organization_id)
    await create_group_member(group_id=group.id, user_id=user.id)

    with client.current_user_as(user):
        response = await client.post("/api/chats", json={"group_id": str(group.id)})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["type"] == "group"
        assert data["name"] == "Dev Team"
        assert data["group"]["id"] == str(group.id)
        assert data["recipient"] is None
        assert data["chat_id"]
        assert data["workspace_id"]


@pytest.mark.asyncio
async def test_create_chat_rejects_both_recipient_and_group(client: AppClient):
    user = await create_user(email="create-both@convictional.com")

    with client.current_user_as(user):
        response = await client.post("/api/chats", json={"recipient_ids": [str(uuid4())], "group_id": str(uuid4())})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        response = await client.post("/api/chats", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_create_chat_with_group_non_member_returns_404(client: AppClient):
    user = await create_user(email="create-nonmem@convictional.com")
    group = await create_group(name="Secret Group", organization_id=user.organization_id)

    with client.current_user_as(user):
        response = await client.post("/api/chats", json={"group_id": str(group.id)})
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_reply_to_appears_in_message_response(client: AppClient):
    user = await create_user(email="reply-send@convictional.com")
    other = await create_user(name="ReplyOther", organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    parent = await create_chat_message(chat_id=chat.id, user_id=other.id, content="Original message")
    reply = await create_chat_message(chat_id=chat.id, user_id=user.id, content="A reply", reply_to_id=parent.id)

    with client.current_user_as(user):
        # Inbox endpoint includes reply_to preview
        response = await client.get(f"/api/chats/{chat.id}/messages")
        assert response.status_code == status.HTTP_200_OK
        messages = response.json()["messages"]

        reply_msg = next(m for m in messages if m["id"] == str(reply.id))
        assert reply_msg["reply_to"] is not None
        assert reply_msg["reply_to"]["id"] == str(parent.id)
        assert reply_msg["reply_to"]["user_name"] == "ReplyOther"
        assert reply_msg["reply_to"]["content_preview"] == "Original message"
        assert reply_msg["reply_to"]["is_deleted"] is False

        # Messages with no reply have null reply_to
        plain_msg = next(m for m in messages if m["id"] == str(parent.id))
        assert plain_msg["reply_to"] is None


@pytest.mark.asyncio
async def test_send_reply_and_response_includes_reply_to(client: AppClient):
    user = await create_user(email="reply-send-resp@convictional.com")
    other = await create_user(name="SenderOther", organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    parent = await create_chat_message(chat_id=chat.id, user_id=other.id, content="Parent message")

    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "My reply", "reply_to_id": str(parent.id)},
        )
        assert response.status_code == status.HTTP_201_CREATED
        msg = response.json()["message"]
        assert msg["reply_to"] is not None
        assert msg["reply_to"]["id"] == str(parent.id)
        assert msg["reply_to"]["user_name"] == "SenderOther"
        assert msg["reply_to"]["content_preview"] == "Parent message"
        assert msg["reply_to"]["is_deleted"] is False


@pytest.mark.asyncio
async def test_edit_ignores_reply_to_id(client: AppClient):
    # Reply target is send-only: a reply_to_id in the edit body is ignored, not re-pointed.
    user = await create_user(email="reply-edit-ignore@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    parent = await create_chat_message(chat_id=chat.id, user_id=other.id, content="Parent")
    reply = await create_chat_message(chat_id=chat.id, user_id=user.id, content="A reply", reply_to_id=parent.id)
    another = await create_chat_message(chat_id=chat.id, user_id=other.id, content="Another")

    with client.current_user_as(user):
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{reply.id}",
            json={"content": "Edited reply", "reply_to_id": str(another.id)},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"]["reply_to"]["id"] == str(parent.id)

    await reply.refresh_from_db()
    assert reply.reply_to_id == parent.id


@pytest.mark.asyncio
async def test_reply_to_cross_chat_rejected(client: AppClient):
    user = await create_user(email="reply-cross@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat1 = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat1.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat1.workspace_id, user_id=other.id)

    chat2 = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=other.id)

    other_chat_message = await create_chat_message(chat_id=chat2.id, user_id=other.id, content="In another chat")

    with client.current_user_as(user):
        # Replying to a message from a different chat is rejected
        response = await client.post(
            f"/api/chats/{chat1.id}/messages",
            json={"content": "Cross-chat reply attempt", "reply_to_id": str(other_chat_message.id)},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_reply_to_nonexistent_id_rejected(client: AppClient):
    user = await create_user(email="reply-ghost@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "Reply to ghost", "reply_to_id": str(uuid4())},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_reply_to_soft_deleted_message_rejected(client: AppClient):
    user = await create_user(email="reply-soft-del@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    parent = await create_chat_message(chat_id=chat.id, user_id=other.id, content="Will be deleted")
    await parent.soft_delete()

    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "Reply to deleted", "reply_to_id": str(parent.id)},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_reply_to_deleted_parent_shows_deleted_preview(client: AppClient):
    user = await create_user(email="reply-del@convictional.com")
    other = await create_user(name="Deleter", organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    parent = await create_chat_message(chat_id=chat.id, user_id=other.id, content="Will be deleted")
    reply = await create_chat_message(chat_id=chat.id, user_id=user.id, content="A reply", reply_to_id=parent.id)

    # Soft-delete the parent
    await parent.soft_delete()

    with client.current_user_as(user):
        # List messages — reply preview shows "deleted" state
        response = await client.get(f"/api/chats/{chat.id}/messages")
        messages = response.json()["messages"]
        reply_data = next(m for m in messages if m["id"] == str(reply.id))
        assert reply_data["reply_to"] is not None
        assert reply_data["reply_to"]["is_deleted"] is True
        assert reply_data["reply_to"]["content_preview"] == "This message was deleted"


@pytest.mark.asyncio
async def test_reply_preview_strips_markdown_and_truncates(client: AppClient):
    user = await create_user(email="reply-preview-fmt@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    parent = await create_chat_message(
        chat_id=chat.id,
        user_id=other.id,
        content="**bold** _italic_ [link](http://x) " + "x" * 500,
    )
    reply = await create_chat_message(chat_id=chat.id, user_id=user.id, content="reply", reply_to_id=parent.id)

    with client.current_user_as(user):
        response = await client.get(f"/api/chats/{chat.id}/messages")
        messages = response.json()["messages"]
        reply_msg = next(m for m in messages if m["id"] == str(reply.id))
        preview = reply_msg["reply_to"]["content_preview"]

    assert preview.startswith("bold italic link")
    assert preview.endswith("…")
    assert len(preview) == 200


@pytest.mark.asyncio
async def test_chats_index_includes_mailbox_state(client: AppClient):
    user = await create_user(email="idx-mailbox@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)
    await create_chat_message(chat_id=chat.id, user_id=other.id, content="Hello")
    await chat.refresh_from_db()
    await Mailbox.sync(chat)

    with client.current_user_as(user):
        response = await client.get("/api/chats")
        data = response.json()
        assert len(data["chats"]) == 1
        item = data["chats"][0]
        assert item["is_unread"] is True
        assert item["is_archived"] is False
        assert item["snoozed_until"] is None


@pytest.mark.asyncio
async def test_create_multi_chat(client: AppClient):
    user = await create_user(email="multi-create@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    with client.current_user_as(user):
        response = await client.post(
            "/api/chats",
            json={"recipient_ids": [str(alice.id), str(bob.id)]},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["type"] == "multi"
        assert "Alice" in data["name"]
        assert "Bob" in data["name"]
        assert data["collaborators"] is not None
        assert len(data["collaborators"]) == 3
        assert data["recipient"] is None
        assert data["group"] is None
        chat_id = data["chat_id"]

        # Dedup: same recipients return same chat
        response = await client.post(
            "/api/chats",
            json={"recipient_ids": [str(bob.id), str(alice.id)]},
        )
        assert response.json()["chat_id"] == chat_id


@pytest.mark.asyncio
async def test_lookup_chat(client: AppClient):
    user = await create_user(email="lookup@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    # Create a multi chat
    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)

    with client.current_user_as(user):
        # Finds multi chat by user set
        ids_param = "&".join(f"user_ids={uid}" for uid in [user.id, alice.id, bob.id])
        response = await client.get(f"/api/chats/lookup?{ids_param}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["matches"]) == 1
        assert data["matches"][0]["id"] == str(chat.id)

        # Returns empty when no match
        response = await client.get(f"/api/chats/lookup?user_ids={user.id}&user_ids={uuid4()}")
        data = response.json()
        assert data["matches"] == []

        # Too few IDs returns empty
        response = await client.get(f"/api/chats/lookup?user_ids={user.id}")
        data = response.json()
        assert data["matches"] == []


@pytest.mark.asyncio
async def test_lookup_chat_returns_match_group_when_group_has_no_chat(client: AppClient):
    user = await create_user(email="lookup-group@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    # Create a group with these members but don't create a chat for it
    group = await create_group(organization_id=user.organization_id, name="Project Team")
    await create_group_member(group_id=group.id, user_id=user.id)
    await create_group_member(group_id=group.id, user_id=alice.id)
    await create_group_member(group_id=group.id, user_id=bob.id)

    with client.current_user_as(user):
        ids_param = "&".join(f"user_ids={uid}" for uid in [user.id, alice.id, bob.id])
        response = await client.get(f"/api/chats/lookup?{ids_param}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["matches"] == []
        assert data["match_group"] is not None
        assert data["match_group"]["id"] == str(group.id)
        assert data["match_group"]["name"] == "Project Team"


@pytest.mark.asyncio
async def test_lookup_chat_returns_match_when_group_has_chat(client: AppClient):
    user = await create_user(email="lookup-group-chat@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)

    # Create a group with a chat
    group = await create_group(organization_id=user.organization_id, name="Design Team")
    await create_group_member(group_id=group.id, user_id=user.id)
    await create_group_member(group_id=group.id, user_id=alice.id)
    group_chat = await create_chat(organization_id=user.organization_id, group_id=group.id)
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=alice.id)

    with client.current_user_as(user):
        ids_param = "&".join(f"user_ids={uid}" for uid in [user.id, alice.id])
        response = await client.get(f"/api/chats/lookup?{ids_param}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["matches"]) == 1
        assert data["matches"][0]["id"] == str(group_chat.id)
        assert data["match_group"] is None


@pytest.mark.asyncio
async def test_lookup_chat_returns_all_chats_containing_selected_users(client: AppClient):
    user = await create_user(email="lookup-supersets@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    # DM between user and alice
    dm = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id]),
    )
    await create_collaborator(workspace_id=dm.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=dm.workspace_id, user_id=alice.id)
    # Attach a link preview to the DM's last message — the serializer must prefetch
    # link_preview to avoid touching an unawaited QuerySet on the FK relation.
    preview = await LinkPreview.create(
        url="https://example.com",
        url_hash="abc123",
        status=LinkPreviewStatus.READY,
    )
    dm_message = await create_chat_message(
        chat_id=dm.id, user_id=user.id, content="dm hello https://example.com", link_preview_id=preview.id
    )

    # 1-n multi chat between user, alice, and bob
    multi = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=multi.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=multi.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=multi.workspace_id, user_id=bob.id)
    multi_message = await create_chat_message(chat_id=multi.id, user_id=alice.id, content="multi hey")

    # Group-backed chat containing user and alice (plus bob)
    group = await create_group(organization_id=user.organization_id, name="Crew")
    await create_group_member(group_id=group.id, user_id=user.id)
    await create_group_member(group_id=group.id, user_id=alice.id)
    await create_group_member(group_id=group.id, user_id=bob.id)
    group_chat = await create_chat(organization_id=user.organization_id, group_id=group.id, title="Crew")
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=bob.id)
    group_message = await create_chat_message(chat_id=group_chat.id, user_id=bob.id, content="group yo")

    # Stale the exact-member DM so recency alone would sort it last
    await ChatMessage.filter(id=dm_message.id).update(created_at=datetime.now(UTC) - timedelta(hours=3))
    await ChatMessage.filter(id=group_message.id).update(created_at=datetime.now(UTC) - timedelta(hours=2))
    await ChatMessage.filter(id=multi_message.id).update(created_at=datetime.now(UTC))

    with client.current_user_as(user):
        ids_param = "&".join(f"user_ids={uid}" for uid in [user.id, alice.id])
        response = await client.get(f"/api/chats/lookup?{ids_param}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        returned_ids = [m["id"] for m in data["matches"]]
        assert set(returned_ids) == {str(dm.id), str(multi.id), str(group_chat.id)}
        # Exact-membership chat (the DM) always comes first, then supersets by recency
        assert returned_ids[0] == str(dm.id)
        assert returned_ids[1] == str(multi.id)
        assert returned_ids[2] == str(group_chat.id)
        assert data["match_group"] is None


@pytest.mark.asyncio
async def test_add_member(client: AppClient):
    user = await create_user(email="add-member@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)
    carol = await create_user(name="Carol", organization_id=user.organization_id)

    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)

    with client.current_user_as(user):
        # Add member with history sharing
        response = await client.post(
            f"/api/chats/{chat.id}/collaborators",
            json={"user_id": str(carol.id), "share_history": True},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["chat_id"] == str(chat.id)
        assert data["added"] is True

        # Verify member was added
        assert await Collaborator.filter(workspace_id=chat.workspace_id, user_id=carol.id).exists()

        # Already a member returns 422
        response = await client.post(
            f"/api/chats/{chat.id}/collaborators",
            json={"user_id": str(carol.id), "share_history": True},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # User not found returns 404
        response = await client.post(
            f"/api/chats/{chat.id}/collaborators",
            json={"user_id": str(uuid4()), "share_history": True},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # Cannot add to group chat
    group = await create_group(name="Group", organization_id=user.organization_id)
    await create_group_member(group_id=group.id, user_id=user.id)
    group_chat = await create_chat(organization_id=user.organization_id, group_id=group.id)
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=user.id)

    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{group_chat.id}/collaborators",
            json={"user_id": str(alice.id), "share_history": True},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Cannot exceed member cap
    all_ids = [user.id]
    capped_chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=capped_chat.workspace_id, user_id=user.id)
    for _ in range(49):
        u = await create_user(organization_id=user.organization_id)
        all_ids.append(u.id)
        await create_collaborator(workspace_id=capped_chat.workspace_id, user_id=u.id)
    capped_chat.collaborators_hash = Chat.compute_collaborators_hash(all_ids)
    await capped_chat.save(update_fields=["collaborators_hash"])

    extra = await create_user(organization_id=user.organization_id)
    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{capped_chat.id}/collaborators",
            json={"user_id": str(extra.id), "share_history": True},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "50" in response.json()["detail"]


@pytest.mark.asyncio
async def test_add_member_without_history(client: AppClient):
    user = await create_user(email="add-no-hist@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)
    carol = await create_user(name="Carol", organization_id=user.organization_id)

    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)

    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{chat.id}/collaborators",
            json={"user_id": str(carol.id), "share_history": False},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["added"] is False
        # A new chat was created (or found)
        assert data["chat_id"] != str(chat.id)


@pytest.mark.asyncio
async def test_remove_member(client: AppClient):
    user = await create_user(email="remove-member@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)
    carol = await create_user(name="Carol", organization_id=user.organization_id)

    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id, carol.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=carol.id)

    # Materialize a mailbox entry for carol so we can assert the membership-change full
    # Mailbox.sync(chat) (Decision 1) soft-deletes it on removal.
    await create_chat_message(chat_id=chat.id, user_id=user.id, content="hi all")
    await chat.refresh_from_db()
    await Mailbox.sync(chat)
    carol_entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=carol.id)
    assert carol_entry is not None and not carol_entry.is_deleted

    with client.current_user_as(user):
        # Normal remove from 4-person chat
        response = await client.delete(f"/api/chats/{chat.id}/collaborators/{carol.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        assert not await Collaborator.filter(workspace_id=chat.workspace_id, user_id=carol.id).exists()
        await carol_entry.refresh_from_db()
        assert carol_entry.is_deleted

        # Cannot remove from DM (now 3 members, removing one more leaves 2 = DM)
        # First remove bob to get to 2 members, then try to remove alice
        response = await client.delete(f"/api/chats/{chat.id}/collaborators/{bob.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Now it's a 2-person chat (DM), cannot remove
        response = await client.delete(f"/api/chats/{chat.id}/collaborators/{alice.id}")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Cannot remove from group chat
    group = await create_group(name="Group", organization_id=user.organization_id)
    await create_group_member(group_id=group.id, user_id=user.id)
    await create_group_member(group_id=group.id, user_id=alice.id)
    group_chat = await create_chat(organization_id=user.organization_id, group_id=group.id)
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=alice.id)

    with client.current_user_as(user):
        response = await client.delete(f"/api/chats/{group_chat.id}/collaborators/{alice.id}")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_remove_member_morph_conflict(client: AppClient):
    user = await create_user(email="morph-conflict@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    # Create existing DM between user and alice
    dm = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id]),
    )
    await create_collaborator(workspace_id=dm.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=dm.workspace_id, user_id=alice.id)

    # Create 3-person multi chat
    multi = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=multi.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=multi.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=multi.workspace_id, user_id=bob.id)

    with client.current_user_as(user):
        # Removing bob leaves user+alice, which conflicts with existing DM
        response = await client.delete(f"/api/chats/{multi.id}/collaborators/{bob.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        # Multi chat is archived (soft-deleted); the existing DM remains and is now the live DM.
        await multi.refresh_from_db()
        assert multi.is_deleted
        await dm.refresh_from_db()
        assert not dm.is_deleted


@pytest.mark.asyncio
async def test_remove_self_from_chat(client: AppClient):
    user = await create_user(email="leave-chat@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)

    with client.current_user_as(user):
        response = await client.delete(f"/api/chats/{chat.id}/collaborators/{user.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        assert not await Collaborator.filter(workspace_id=chat.workspace_id, user_id=user.id).exists()

    # Cannot leave a DM
    carol = await create_user(name="Carol", organization_id=user.organization_id)
    dm = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, carol.id]),
    )
    await create_collaborator(workspace_id=dm.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=dm.workspace_id, user_id=carol.id)

    with client.current_user_as(user):
        response = await client.delete(f"/api/chats/{dm.id}/collaborators/{user.id}")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_rename_chat(client: AppClient):
    user = await create_user(email="rename-chat@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)

    with client.current_user_as(user):
        # Set custom title — response includes resolved chat_title for the React header
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "Project Chat"})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == "Project Chat"
        assert data["chat_title"] == "Project Chat"

        # Clear title (empty string clears, matches null) — chat_title falls back to member names
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": ""})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] is None
        assert data["chat_title"] == "Alice, Bob"

        # Whitespace-only is rejected (prevents silent clear on fat-fingered spacebar)
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "   "})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # 200-char boundary: accepted at the limit, rejected one over (Pydantic max_length)
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "x" * 200})
        assert response.status_code == status.HTTP_200_OK
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "x" * 201})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Cannot rename a DM
    dm = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id]),
    )
    await create_collaborator(workspace_id=dm.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=dm.workspace_id, user_id=alice.id)

    with client.current_user_as(user):
        response = await client.patch(f"/api/chats/{dm.id}", json={"title": "My DM"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Cannot rename a group chat
    group = await create_group(name="Group", organization_id=user.organization_id)
    await create_group_member(group_id=group.id, user_id=user.id)
    group_chat = await create_chat(organization_id=user.organization_id, group_id=group.id)
    await create_collaborator(workspace_id=group_chat.workspace_id, user_id=user.id)

    with client.current_user_as(user):
        response = await client.patch(f"/api/chats/{group_chat.id}", json={"title": "New Name"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_rename_chat_records_event(client: AppClient):
    # Rename records a CHAT_RENAMED workspace event (with the new title in details, creator = actor)
    # so the mailbox preview can phrase the activity line. Clearing the title records title=None.
    user = await create_user(email="rename-event@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)

    with client.current_user_as(user):
        assert (await client.patch(f"/api/chats/{chat.id}", json={"title": "Project Chat"})).status_code == 200
        assert (await client.patch(f"/api/chats/{chat.id}", json={"title": ""})).status_code == 200

    events = (
        await Event.filter(workspace_id=chat.workspace_id, action=EventAction.CHAT_RENAMED)
        .order_by("created_at")
        .all()
    )
    assert [e.details["title"] for e in events] == ["Project Chat", None]
    assert all(e.creator_id == user.id for e in events)


@pytest.mark.asyncio
async def test_rename_chat_name_conflict(client: AppClient):
    user = await create_user(email="rename-conflict@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)
    carol = await create_user(name="Carol", organization_id=user.organization_id)

    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)

    # Existing group with a name in the same org
    conflicting_group = await create_group(name="Project Alpha", organization_id=user.organization_id)
    await create_group_member(group_id=conflicting_group.id, user_id=user.id)

    # Another multi chat that already owns a custom name
    other_chat = await create_chat(
        organization_id=user.organization_id,
        title="Team Sync",
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, carol.id]),
    )
    await create_collaborator(workspace_id=other_chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=other_chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=other_chat.workspace_id, user_id=carol.id)

    # A named chat in the same org that `user` is NOT a member of. The membership
    # scoping in _name_conflicts exists so this can't be used as an existence oracle
    # — renaming to the same name must succeed for the outsider.
    outsider_chat = await create_chat(
        organization_id=user.organization_id,
        title="Hidden Chat",
        collaborators_hash=Chat.compute_collaborators_hash([alice.id, bob.id, carol.id]),
    )
    await create_collaborator(workspace_id=outsider_chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=outsider_chat.workspace_id, user_id=bob.id)
    await create_collaborator(workspace_id=outsider_chat.workspace_id, user_id=carol.id)

    # A chat in a different organization with a conflicting name — must not leak across orgs
    other_org = await create_organization()
    other_org_user = await create_user(organization_id=other_org.id)
    other_org_chat = await create_chat(
        organization_id=other_org.id,
        title="Cross Org Name",
        collaborators_hash=Chat.compute_collaborators_hash([other_org_user.id]),
    )
    await create_collaborator(workspace_id=other_org_chat.workspace_id, user_id=other_org_user.id)
    other_org_group = await create_group(name="Cross Org Group", organization_id=other_org.id)
    await create_group_member(group_id=other_org_group.id, user_id=other_org_user.id)

    with client.current_user_as(user):
        # Conflicts with an existing group name (case-insensitive)
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "project alpha"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # Conflicts with another chat's custom title
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "Team Sync"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # Renaming to its own existing title is fine (no-op)
        await Chat.filter(id=chat.id).update(title="Keep This")
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "Keep This"})
        assert response.status_code == status.HTTP_200_OK

        # A fresh title is accepted
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "Brand New Name"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["title"] == "Brand New Name"

        # Non-collaborator oracle: a named chat in this org that `user` isn't in must not conflict.
        # Regression test for ChatFilters.by_collaborator scoping in _title_conflicts.
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "Hidden Chat"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["title"] == "Hidden Chat"

        # Cross-org isolation: names in another organization must not conflict.
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "Cross Org Name"})
        assert response.status_code == status.HTTP_200_OK
        response = await client.patch(f"/api/chats/{chat.id}", json={"title": "Cross Org Group"})
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_chat_list_includes_multi(client: AppClient):
    user = await create_user(email="list-multi@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await create_chat_message(chat_id=chat.id, user_id=alice.id, content="Hello multi")

    with client.current_user_as(user):
        response = await client.get("/api/chats")
        data = response.json()
        assert len(data["chats"]) == 1
        item = data["chats"][0]
        assert item["type"] == "multi"
        assert item["collaborator_count"] == 3
        assert item["collaborators"] is not None
        assert "Alice" in item["name"]
        assert "Bob" in item["name"]


@pytest.mark.asyncio
async def test_contacts_not_hidden_by_multi_chat(client: AppClient):
    user = await create_user(email="contacts-multi@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    # Create a multi chat with alice and bob (not a DM)
    chat = await create_chat(
        organization_id=user.organization_id,
        collaborators_hash=Chat.compute_collaborators_hash([user.id, alice.id, bob.id]),
    )
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await create_chat_message(chat_id=chat.id, user_id=alice.id, content="Hi")

    with client.current_user_as(user):
        response = await client.get("/api/chats/contacts")
        data = response.json()
        names = [c["name"] for c in data["contacts"]]
        # Alice and Bob should still appear as contacts since they only share a multi chat, not a DM
        assert "Alice" in names
        assert "Bob" in names


async def _seed_visit(user_id, workspace_id, last_visit_at):
    # The unread pivot is Visit.last_event_id → that event's created_at, so seed a matching Event.
    event = await Event.create(
        workspace_id=workspace_id,
        recordable_id=uuid4(),
        recordable_type="Chat",
        action=EventAction.CHAT_MESSAGE_CREATED,
        created_at=last_visit_at,
        updated_at=last_visit_at,
    )
    visit = await Visit.create(
        user_id=user_id,
        workspace_id=workspace_id,
        last_visit_at=last_visit_at,
        last_event_id=event.id,
    )
    await Visit.filter(id=visit.id).update(updated_at=last_visit_at)
    return visit


@pytest.mark.asyncio
async def test_chat_detail_includes_last_read_at_and_unread_count(client: AppClient):
    org = await create_organization()
    user = await create_user(organization_id=org.id, email="unread-detail@convictional.com")
    other = await create_user(organization_id=org.id)

    read_time = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)

    chat = await create_chat(organization_id=org.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)
    await _seed_visit(user.id, chat.workspace_id, read_time)
    await create_chat_message(chat_id=chat.id, user_id=other.id, created_at=read_time + timedelta(minutes=1))
    await create_chat_message(chat_id=chat.id, user_id=other.id, created_at=read_time + timedelta(minutes=2))
    await create_chat_message(chat_id=chat.id, user_id=other.id, created_at=read_time + timedelta(minutes=3))

    with client.current_user_as(user):
        response = await client.get(f"/api/chats/{chat.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["last_read_at"] == read_time.isoformat()
        assert data["unread_message_count"] == 3

    # User with no Visit gets null
    new_user = await create_user(organization_id=org.id)
    chat2 = await create_chat(organization_id=org.id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=new_user.id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=other.id)

    with client.current_user_as(new_user):
        response = await client.get(f"/api/chats/{chat2.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["last_read_at"] is None
        assert data["unread_message_count"] == 0


@pytest.mark.asyncio
async def test_chat_detail_excludes_own_messages_from_unread_count(client: AppClient):
    org = await create_organization()
    user = await create_user(organization_id=org.id, email="self-unread@convictional.com")
    other = await create_user(organization_id=org.id)

    read_time = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)

    chat = await create_chat(organization_id=org.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)
    await _seed_visit(user.id, chat.workspace_id, read_time)
    # Mix of messages: two from current user, one from the other
    await create_chat_message(chat_id=chat.id, user_id=user.id, created_at=read_time + timedelta(minutes=1))
    await create_chat_message(chat_id=chat.id, user_id=other.id, created_at=read_time + timedelta(minutes=2))
    await create_chat_message(chat_id=chat.id, user_id=user.id, created_at=read_time + timedelta(minutes=3))

    with client.current_user_as(user):
        response = await client.get(f"/api/chats/{chat.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Only the message from `other` counts as unread — the user's own messages don't
        assert data["unread_message_count"] == 1


@pytest.mark.asyncio
async def test_chat_detail_supports_mentions_per_chat_type(client: AppClient):
    user = await create_user(email="mentions-url@convictional.com")
    org_id = user.organization_id
    others = [await create_user(organization_id=org_id) for _ in range(2)]

    async def make_chat(member_count: int, *, group_id: UUID | None = None) -> Chat:
        chat = await create_chat(organization_id=org_id, group_id=group_id)
        members = [user] + others[: member_count - 1]
        for member in members:
            await create_collaborator(workspace_id=chat.workspace_id, user_id=member.id)
        return chat

    self_chat = await make_chat(1)
    dm_chat = await make_chat(2)
    multi_chat = await make_chat(3)
    group = await create_group(organization_id=org_id)
    await create_group_member(group_id=group.id, user_id=user.id)
    group_chat = await make_chat(1, group_id=group.id)

    with client.current_user_as(user):
        # DM and self chats don't support @mentions — there's no useful @mention target.
        # Candidates now come from the organizationMembers store, filtered to the chat's
        # collaborators, so the API only advertises whether mentions are available.
        assert (await client.get(f"/api/chats/{self_chat.id}")).json()["supports_mentions"] is False
        assert (await client.get(f"/api/chats/{dm_chat.id}")).json()["supports_mentions"] is False

        # Multi and group chats support mentions
        assert (await client.get(f"/api/chats/{multi_chat.id}")).json()["supports_mentions"] is True
        assert (await client.get(f"/api/chats/{group_chat.id}")).json()["supports_mentions"] is True


@pytest.mark.asyncio
async def test_chat_message_mentions_in_multi_chat(client: AppClient, background_jobs: InlineJobs):
    """Create resolves to existing members; edit is idempotent; edit can add new mentions."""
    user = await create_user(name="Sender", email="mentions-multi@convictional.com")
    alice = await create_user(name="Alice", organization_id=user.organization_id)
    bob = await create_user(name="Bob", organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    for member in [user, alice, bob]:
        await create_collaborator(workspace_id=chat.workspace_id, user_id=member.id)
        await chat.workspace.subscribe(member.id)

    background_jobs.reset()

    with client.current_user_as(user):
        # Create a message mentioning Alice — one Mention row, one notification job for Alice
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "Hey @[Alice], take a look"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        message_id = response.json()["message"]["id"]

        mentions = await Mention.filter(workspace_id=chat.workspace_id).all()
        assert [m.mentioned_id for m in mentions] == [alice.id]

        # Alice's mailbox row is materialized by the per-event SyncMailboxJob,
        # not by any per-mention path. Chat mention notifications are push-only
        # (Notifier.notify_mentions), not a separate mailbox sync.
        alice_entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=alice.id)
        assert alice_entry is not None
        assert alice_entry.is_inbox
        assert alice_entry.is_unread

        # Edit keeping the same @[Alice] — no new Mention row.
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message_id}",
            json={"content": "Hey @[Alice], take another look"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert await Mention.filter(workspace_id=chat.workspace_id).count() == 1

        # Edit with the same @[Alice] mentioned twice in one edit — still exactly one Mention row.
        # MentionResolver dedupes mentions per (recordable, user), so a duplicate token resolves once.
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message_id}",
            json={"content": "@[Alice] thanks @[Alice]"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert await Mention.filter(workspace_id=chat.workspace_id, mentioned_id=alice.id).count() == 1

        # Re-mention an already-delivered user — Notifier.notify_mentions filters out
        # mentions with delivered_at set, so no new SendMentionJob fires for Alice.
        alice_mention = await Mention.filter(workspace_id=chat.workspace_id, mentioned_id=alice.id).first()
        assert alice_mention is not None
        await alice_mention.mark_delivered()

        background_jobs.reset()
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message_id}",
            json={"content": "circling back @[Alice]"},
        )
        assert response.status_code == status.HTTP_200_OK
        mention_jobs = background_jobs.all_completed_jobs_by_type(SendMentionJob)
        mention_job_user_ids = {(await Mention.get(id=j.job_definition.mention_id)).mentioned_id for j in mention_jobs}
        assert alice.id not in mention_job_user_ids, "Already-delivered mention must not enqueue a new SendMentionJob"

        # Edit to add @[Bob] — one new Mention row for Bob, Alice's row unchanged.
        # Bob's mailbox entry is materialized by the edit's SyncMailboxJob.
        background_jobs.reset()
        response = await client.patch(
            f"/api/chats/{chat.id}/messages/{message_id}",
            json={"content": "Hey @[Alice] and @[Bob]"},
        )
        assert response.status_code == status.HTTP_200_OK
        mentioned_ids = {m.mentioned_id for m in await Mention.filter(workspace_id=chat.workspace_id).all()}
        assert mentioned_ids == {alice.id, bob.id}
        assert await Mention.filter(workspace_id=chat.workspace_id).count() == 2

        bob_entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=bob.id)
        assert bob_entry is not None
        assert bob_entry.is_inbox
        assert bob_entry.is_unread


@pytest.mark.asyncio
async def test_chat_message_mention_does_not_add_non_collaborator(client: AppClient, background_jobs: InlineJobs):
    """Mentioning a non-member must not silently add them — Chat invariants own membership."""
    user = await create_user(name="Sender", email="mentions-noadd@convictional.com")
    member = await create_user(name="Member", organization_id=user.organization_id)
    outsider = await create_user(name="Outsider", organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    for m in [user, member]:
        await create_collaborator(workspace_id=chat.workspace_id, user_id=m.id)
        await chat.workspace.subscribe(m.id)

    original_hash = chat.collaborators_hash
    background_jobs.reset()

    with client.current_user_as(user):
        response = await client.post(
            f"/api/chats/{chat.id}/messages",
            json={"content": "Hey @[Outsider], join us"},
        )
        assert response.status_code == status.HTTP_201_CREATED

    # Outsider is not added; no Mention row for them; collaborators_hash unchanged
    collaborator_user_ids = await Collaborator.filter(workspace_id=chat.workspace_id).values_list("user_id", flat=True)
    assert outsider.id not in collaborator_user_ids
    assert not await Mention.filter(workspace_id=chat.workspace_id, mentioned_id=outsider.id).exists()
    await chat.refresh_from_db()
    assert chat.collaborators_hash == original_hash


@pytest.mark.asyncio
async def test_chat_message_mentions_skipped_in_dm_and_self(client: AppClient, background_jobs: InlineJobs):
    """DM and SELF chats hide the picker; raw @[Name] text in content must not resolve server-side."""
    user = await create_user(name="DMSender", email="mentions-dm@convictional.com")
    recipient = await create_user(name="Recipient", organization_id=user.organization_id)

    dm = await create_chat(organization_id=user.organization_id)
    for m in [user, recipient]:
        await create_collaborator(workspace_id=dm.workspace_id, user_id=m.id)
        await dm.workspace.subscribe(m.id)

    self_chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=self_chat.workspace_id, user_id=user.id)
    await self_chat.workspace.subscribe(user.id)

    background_jobs.reset()

    with client.current_user_as(user):
        # Raw @[Name] text in a DM does not produce a Mention row
        response = await client.post(
            f"/api/chats/{dm.id}/messages",
            json={"content": "Hi @[Recipient]"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert not await Mention.filter(workspace_id=dm.workspace_id).exists()

        # Same for self chats
        response = await client.post(
            f"/api/chats/{self_chat.id}/messages",
            json={"content": "Note to @[DMSender]"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert not await Mention.filter(workspace_id=self_chat.workspace_id).exists()

        # Edit path is also gated — adding @[Name] on edit in a DM doesn't resolve
        message = await create_chat_message(chat_id=dm.id, user_id=user.id, content="hi")
        response = await client.patch(
            f"/api/chats/{dm.id}/messages/{message.id}",
            json={"content": "edited @[Recipient]"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert not await Mention.filter(workspace_id=dm.workspace_id).exists()


@pytest.mark.asyncio
async def test_chats_index_pagination(client: AppClient):
    per_page = settings.pagination_default_per_page
    client_user = await client.get_default_user()
    other_user = await create_user(organization_id=client_user.organization_id)
    total = per_page + 5
    for _ in range(total):
        chat = await create_chat(organization_id=client_user.organization_id)
        await create_collaborator(workspace_id=chat.workspace_id, user_id=client_user.id)
        await create_collaborator(workspace_id=chat.workspace_id, user_id=other_user.id)
        await create_chat_message(chat_id=chat.id, user_id=other_user.id)

    response = await client.get("/api/chats")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["chats"]) == per_page
    assert data["has_more"] is True
    assert data["next_cursor"] is not None
    first_page_ids = {c["id"] for c in data["chats"]}

    response = await client.get(f"/api/chats?cursor={data['next_cursor']}")
    page2 = response.json()
    assert len(page2["chats"]) == 5
    assert page2["has_more"] is False
    assert page2["next_cursor"] is None
    assert first_page_ids.isdisjoint({c["id"] for c in page2["chats"]})
