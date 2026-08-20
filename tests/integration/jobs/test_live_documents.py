from datetime import UTC, datetime, timedelta
from uuid import uuid4 as generate_uuid

import pytest
from pycrdt import Doc, Map, Text

from app.jobs.content import IndexDocumentJob, IndexMeetingJob
from app.jobs.live_documents import MergeAndNotifyLiveDocuments
from app.models.collaboration.live import LiveDocumentUpdate
from app.models.collaboration.workspace import MENTION_EXCERPT_LENGTH, Collaborator, Event, Mention
from config.enums import EventAction
from infra.jobs import JobsOutbox
from infra.messaging import Topic
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_document,
    create_meeting,
    create_organization,
    create_user,
)


@pytest.mark.asyncio
async def test_merge_and_notify_meeting_agendas(client: AppClient, email_delivery):
    """Test that meeting agenda edits trigger MEETING_AGENDA_UPDATED notifications"""
    email_delivery.reset()

    organization = await create_organization()
    editor1 = await create_user(organization_id=organization.id, name="Editor One", email="editor1@example.com")
    editor2 = await create_user(organization_id=organization.id, name="Editor Two", email="editor2@example.com")
    collaborator = await create_user(
        organization_id=organization.id, name="Collaborator", email="collaborator@example.com"
    )

    meeting = await create_meeting(organization_id=organization.id, creator_id=editor1.id)
    await Collaborator.create(workspace_id=meeting.workspace_id, user_id=editor2.id)
    await Collaborator.create(workspace_id=meeting.workspace_id, user_id=collaborator.id)

    inline_attachment = await create_attachment(
        user_id=editor1.id,
        workspace_id=meeting.workspace_id,
        claim_id=generate_uuid(),
        comment_gid=None,
    )

    topic = Topic("meeting_agenda", meeting_id=str(meeting.id))
    stable_time = datetime.now(UTC) - timedelta(minutes=20)

    doc1: Doc = Doc()
    text1 = doc1.get("markdown", type=Text)
    text1 += (
        f"# Meeting Agenda\n\n- Item 1: Discuss quarterly goals\n"
        f"![chart](/workspaces/{meeting.workspace_id}/attachments/{inline_attachment.id}/download)"
    )

    with doc1.transaction():
        editors: Map = doc1.get("editors", type=Map)
        editors[str(editor1.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc1.get_update(),
        created_at=stable_time,
    )

    doc2: Doc = Doc()
    doc2.apply_update(doc1.get_update())
    text2 = doc2.get("markdown", type=Text)
    text2 += "\n- Item 2: Review budget allocations"

    with doc2.transaction():
        editors2: Map = doc2.get("editors", type=Map)
        editors2[str(editor2.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc2.get_update(doc1.get_update()),
        created_at=stable_time + timedelta(minutes=1),
    )

    updates = await LiveDocumentUpdate.filter(topic_name=topic.name).all()
    assert len(updates) >= 2

    job = MergeAndNotifyLiveDocuments(minutes=15)
    async with JobsOutbox() as outbox:
        await job.perform()
        enqueued_job_types = {enqueued.job_type for enqueued in outbox.jobs}

    # Agenda edits arrive over WebSocket and never hit the HTTP index dependency, so the merge job
    # is what re-indexes the meeting for search/MCP.
    assert IndexMeetingJob.job_type() in enqueued_job_types

    events = await Event.filter(
        Event.filters.by_workspace(meeting.workspace_id) & Event.filters.by_action(EventAction.MEETING_AGENDA_UPDATED)
    ).all()
    assert len(events) >= 1

    event = events[0]
    assert event.details is not None
    assert len(event.details["editor_ids"]) == 2
    assert "Meeting Agenda" in event.details["document_content"]
    assert "quarterly goals" in event.details["document_content"]
    assert "budget allocations" in event.details["document_content"]

    # Inline attachments referenced in agenda markdown are claimed during the merge
    await inline_attachment.refresh_from_db()
    assert inline_attachment.claim_id is None


@pytest.mark.asyncio
async def test_document_mentions(client: AppClient, email_delivery):
    """Test that @mentions in document content trigger mention notifications"""
    email_delivery.reset()

    organization = await create_organization()
    editor = await create_user(organization_id=organization.id, name="Editor One", email="doc-editor1@example.com")
    mentioned_user = await create_user(
        organization_id=organization.id, name="Bob Clams", email="doc-mentioned@example.com"
    )

    document = await create_document(organization_id=organization.id, creator_id=editor.id, title="Project Plan")
    await Collaborator.create(workspace_id=document.workspace_id, user_id=mentioned_user.id)

    inline_attachment = await create_attachment(
        user_id=editor.id,
        workspace_id=document.workspace_id,
        claim_id=generate_uuid(),
        comment_gid=None,
    )

    topic = Topic("document", document_id=str(document.id))
    stable_time = datetime.now(UTC) - timedelta(minutes=20)

    # Editor writes a long body that mentions another user deep in the middle.
    # OPENING_SENTINEL / CLOSING_SENTINEL sit far (> the excerpt window) from the
    # mention, so a correct excerpt keeps NEARBYTOKEN but drops both sentinels.
    doc1: Doc = Doc()
    text1 = doc1.get("markdown", type=Text)
    long_intro = "OPENING_SENTINEL. " + ("This is a long paragraph of document content. " * 20)
    long_outro = ("Trailing discussion continues here. " * 20) + "CLOSING_SENTINEL."
    text1 += (
        f"# Project Plan\n\n{long_intro}\n\n"
        f"Hey @[Bob Clams] NEARBYTOKEN, please review this section.\n\n{long_outro}\n"
        f"![diagram](/workspaces/{document.workspace_id}/attachments/{inline_attachment.id}/download)"
    )

    with doc1.transaction():
        editors: Map = doc1.get("editors", type=Map)
        editors[str(editor.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc1.get_update(),
        created_at=stable_time,
    )

    # Second update to trigger merge (needs > 1 update)
    doc2: Doc = Doc()
    doc2.apply_update(doc1.get_update())
    text2 = doc2.get("markdown", type=Text)
    text2 += "\n\nMore details here."

    with doc2.transaction():
        editors2: Map = doc2.get("editors", type=Map)
        editors2[str(editor.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc2.get_update(doc1.get_update()),
        created_at=stable_time + timedelta(minutes=1),
    )

    job = MergeAndNotifyLiveDocuments(minutes=15)
    async with JobsOutbox() as outbox:
        await job.perform()
        enqueued_job_types = {enqueued.job_type for enqueued in outbox.jobs}

    # Body edits arrive over WebSocket and never hit the HTTP index dependency, so the merge job
    # is what re-indexes the document for search/MCP.
    assert IndexDocumentJob.job_type() in enqueued_job_types

    # Verify a Mention was created for the mentioned user
    mentions = await Mention.filter(workspace_id=document.workspace_id, mentioned_id=mentioned_user.id).all()
    assert len(mentions) == 1
    assert mentions[0].creator_id == editor.id
    # Stored content is a channel-agnostic window around the mention: raw @[Name]
    # markers intact, the far-away sentinels dropped, bounded near the cap — so it
    # never carries the whole document body.
    content = mentions[0].content
    assert "@[Bob Clams]" in content  # raw marker preserved in storage
    assert "NEARBYTOKEN" in content
    assert "OPENING_SENTINEL" not in content
    assert "CLOSING_SENTINEL" not in content
    assert len(content) <= MENTION_EXCERPT_LENGTH + 2

    # The email renders that excerpt with the marker humanized + bolded, carrying
    # the nearby context but not the whole document.
    sent = email_delivery.by_recipient(mentioned_user.email)
    assert len(sent) == 1
    assert "@Bob Clams" in sent[0].html and "@[Bob Clams]" not in sent[0].html
    assert "NEARBYTOKEN" in sent[0].html
    assert "OPENING_SENTINEL" not in sent[0].html
    assert "CLOSING_SENTINEL" not in sent[0].html
    assert "OPENING_SENTINEL" not in sent[0].html
    assert "CLOSING_SENTINEL" not in sent[0].html

    # Inline attachments referenced in the document markdown are claimed during merge.
    await inline_attachment.refresh_from_db()
    assert inline_attachment.claim_id is None

    # Verify NO content-updated event was created (documents use mentions, not content notifications)
    events = await Event.filter(Event.filters.by_workspace(document.workspace_id)).all()
    content_events = [e for e in events if "document_content" in (e.details or {})]
    assert len(content_events) == 0

    # Running the job again should NOT create duplicate mentions
    # (need new updates to trigger merge)
    doc3: Doc = Doc()
    doc3.apply_update(doc2.get_update(doc1.get_update()))
    text3 = doc3.get("markdown", type=Text)
    text3 += "\nAnother line."

    with doc3.transaction():
        editors3: Map = doc3.get("editors", type=Map)
        editors3[str(editor.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc3.get_update(),
        created_at=datetime.now(UTC) - timedelta(minutes=20),
    )

    doc4: Doc = Doc()
    doc4.apply_update(doc3.get_update())
    text4 = doc4.get("markdown", type=Text)
    text4 += "\nYet another line."

    with doc4.transaction():
        editors4: Map = doc4.get("editors", type=Map)
        editors4[str(editor.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc4.get_update(doc3.get_update()),
        created_at=datetime.now(UTC) - timedelta(minutes=19),
    )

    async with JobsOutbox():
        await job.perform()

    mentions_after = await Mention.filter(workspace_id=document.workspace_id, mentioned_id=mentioned_user.id).all()
    assert len(mentions_after) == 1, "Should not create duplicate mentions"
