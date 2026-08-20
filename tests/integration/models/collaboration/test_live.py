import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4 as generate_uuid

import pytest
from freezegun import freeze_time
from pycrdt import Doc, Text

from app.models.collaboration.live import (
    LiveDocument,
    LiveDocumentFilters,
    LiveDocumentUpdate,
    Presence,
    Typing,
    workspace_scope_key,
)
from infra.messaging import Topic


@pytest.mark.asyncio
async def test_live_document_update_ordering():
    """Test that updates are ordered by creation time"""
    topic = Topic("test_document", document_id="1")

    # Create multiple updates
    update_data_1 = b"update1"
    update_data_2 = b"update2"
    update_data_3 = b"update3"

    update1 = await LiveDocumentUpdate.create(topic_name=topic.name, update_data=update_data_1)
    await asyncio.sleep(0.01)  # Ensure different timestamps

    update2 = await LiveDocumentUpdate.create(topic_name=topic.name, update_data=update_data_2)
    await asyncio.sleep(0.01)

    update3 = await LiveDocumentUpdate.create(topic_name=topic.name, update_data=update_data_3)

    # Verify ordering
    updates = await LiveDocumentUpdate.filter(LiveDocumentFilters.for_topic(topic)).all()
    assert len(updates) == 3
    assert updates[0].id == update1.id
    assert updates[1].id == update2.id
    assert updates[2].id == update3.id


@pytest.mark.asyncio
async def test_live_document_from_topic():
    """Test creating LiveDocument from stored updates"""
    topic = Topic("test_document", document_id="hello-world")

    # Create a series of CRDT updates
    doc: Doc = Doc()
    text = doc.get("markdown", type=Text)

    # First update: add "Hello "
    text += "Hello "
    update1 = doc.get_update()
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=update1)

    # Second update: add "World" (differential)
    prev_state = doc.get_update()
    text += "World"
    update2 = doc.get_update(prev_state)
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=update2)

    # Third update: add "!" (differential)
    prev_state = doc.get_update()
    text += "!"
    update3 = doc.get_update(prev_state)
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=update3)

    # Reconstruct document from stored updates
    reconstructed_doc = await LiveDocument.for_topic(topic)

    # Verify content matches
    assert reconstructed_doc.markdown == "Hello World!"


@pytest.mark.asyncio
async def test_apply_all_updates_to_document():
    """Test applying stored updates to a document"""
    topic = Topic("test_document", document_id="first-second")

    # Create and store updates
    doc: Doc = Doc()
    text = doc.get("markdown", type=Text)
    text += "First "
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=doc.get_update())

    prev_state = doc.get_update()
    text += "Second"
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=doc.get_update(prev_state))

    # Apply updates to a new document
    new_doc: Doc = Doc()
    await LiveDocumentUpdate.apply_all_updates(new_doc, topic)

    # Verify content
    new_text = new_doc.get("markdown", type=Text)
    assert str(new_text) == "First Second"


@pytest.mark.asyncio
async def test_multiple_documents_isolation():
    """Test that updates for different documents are isolated"""
    topic_1 = Topic("test_document", document_id="1")
    topic_2 = Topic("test_document", document_id="2")

    # Create updates for first document
    doc1: Doc = Doc()
    text1 = doc1.get("markdown", type=Text)
    text1 += "Document 1 content"
    await LiveDocumentUpdate.create(topic_name=topic_1.name, update_data=doc1.get_update())

    # Create updates for second document
    doc2: Doc = Doc()
    text2 = doc2.get("markdown", type=Text)
    text2 += "Document 2 content"
    await LiveDocumentUpdate.create(topic_name=topic_2.name, update_data=doc2.get_update())

    # Verify isolation
    # Verify content isolation
    reconstructed_1 = await LiveDocument.for_topic(topic_1)
    reconstructed_2 = await LiveDocument.for_topic(topic_2)

    assert reconstructed_1.markdown == "Document 1 content"
    assert reconstructed_2.markdown == "Document 2 content"


@pytest.mark.asyncio
async def test_get_topics_stable_for():
    meeting_topic = Topic("meeting_agenda", meeting_id="123")
    other_topic = Topic("other_stream", document_id="456")

    old_time = datetime.now(UTC) - timedelta(minutes=20)

    doc1: Doc = Doc()
    text1 = doc1.get("markdown", type=Text)
    text1 += "Old meeting agenda content"
    old_update = await LiveDocumentUpdate.create(
        topic_name=meeting_topic.name, update_data=doc1.get_update(), created_at=old_time
    )

    doc2: Doc = Doc()
    text2 = doc2.get("markdown", type=Text)
    text2 += "Old other content"
    await LiveDocumentUpdate.create(topic_name=other_topic.name, update_data=doc2.get_update(), created_at=old_time)

    recent_time = datetime.now(UTC) - timedelta(minutes=5)

    recent_meeting_topic = Topic("meeting_agenda", meeting_id="789")
    doc3: Doc = Doc()
    text3 = doc3.get("markdown", type=Text)
    text3 += "Recent meeting agenda content"
    recent_update = await LiveDocumentUpdate.create(
        topic_name=recent_meeting_topic.name, update_data=doc3.get_update(), created_at=recent_time
    )

    await LiveDocumentUpdate.filter(id=old_update.id).update(created_at=old_time)
    await LiveDocumentUpdate.filter(id=recent_update.id).update(created_at=recent_time)

    await old_update.refresh_from_db()
    await recent_update.refresh_from_db()

    stable_topics = await LiveDocument.get_topics_stable_for(minutes=15, stream="meeting_agenda")
    stable_topic_names = [topic.name for topic in stable_topics]

    assert recent_meeting_topic.name not in stable_topic_names, (
        f"Recent topic {recent_meeting_topic.name} should not be stable"
    )
    assert meeting_topic.name in stable_topic_names, f"Old topic {meeting_topic.name} should be stable"
    assert other_topic.name not in stable_topic_names, (
        f"Other stream topic {other_topic.name} should not be included when filtering by meeting_agenda stream"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("activity_class", [Typing, Presence])
async def test_live_activity_basic_operations(activity_class, use_postgres_cache):
    workspace_id = generate_uuid()
    user_id = generate_uuid()

    activity_cache = activity_class(scope_key=workspace_scope_key(workspace_id))

    # Test basic add and remove
    user_ids = await activity_cache.add_user(user_id)
    assert user_ids == [user_id]

    user_ids = await activity_cache.remove_user(user_id)
    assert user_ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize("activity_class", [Typing, Presence])
async def test_live_activity_multiple_users(activity_class, use_postgres_cache):
    workspace_id = generate_uuid()
    user1_id = generate_uuid()
    user2_id = generate_uuid()

    activity_cache = activity_class(scope_key=workspace_scope_key(workspace_id))

    # Add first user
    user_ids = await activity_cache.add_user(user1_id)
    assert len(user_ids) == 1
    assert user1_id in user_ids

    # Add second user
    user_ids = await activity_cache.add_user(user2_id)
    assert len(user_ids) == 2
    assert user1_id in user_ids
    assert user2_id in user_ids

    # Remove first user
    user_ids = await activity_cache.remove_user(user1_id)
    assert len(user_ids) == 1
    assert user2_id in user_ids
    assert user1_id not in user_ids

    # Remove second user
    user_ids = await activity_cache.remove_user(user2_id)
    assert user_ids == []


@pytest.mark.asyncio
async def test_presence_drops_users_with_expired_heartbeat(use_postgres_cache):
    workspace_id = generate_uuid()
    user_id = generate_uuid()
    presence = Presence(scope_key=workspace_scope_key(workspace_id))

    with freeze_time("2026-01-01 12:00:00") as frozen_time:
        assert await presence.add_user(user_id) == [user_id]

        # Past the 100s heartbeat timeout but within the 5m activity window: the
        # user's timestamp key has expired, so they drop out of the active set.
        frozen_time.tick(timedelta(seconds=101))
        assert await presence.get_active_user_ids() == []
