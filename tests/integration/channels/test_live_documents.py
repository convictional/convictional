import asyncio
import base64
from uuid import uuid4

import pytest
from pycrdt import Awareness, Doc, Text, create_update_message

from app.channels.live_documents import SharedDocument
from app.models.collaboration.live import LiveDocument, LiveDocumentUpdate
from config.enums import ChannelMessageType
from infra.messaging import Topic


async def _create_shared_document(topic: Topic, initial_update: bytes) -> SharedDocument:
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=initial_update)
    live_doc = await LiveDocument.for_topic(topic)
    awareness = Awareness(live_doc)
    shared_doc = SharedDocument(document=live_doc, topic=topic, awareness=awareness)
    await shared_doc.start()
    await shared_doc._ready.wait()
    return shared_doc


def _make_broadcast_payload(topic: Topic, diff_update: bytes) -> dict:
    sync_msg = create_update_message(diff_update)
    wire_data = sync_msg[1:]
    return {
        "type": ChannelMessageType.LIVE_DOCUMENT_SYNC,
        "topic_stream": topic.stream,
        "topic_params": topic.params,
        "data": base64.b64encode(wire_data).decode("utf-8"),
    }


@pytest.mark.asyncio
async def test_server_sync_update_does_not_create_duplicate_db_records():
    """Server-broadcast updates (from another instance) should NOT create DB records,
    because the originating instance already persisted the update.
    """
    topic = Topic("test_document", document_id=str(uuid4()))

    initial_doc: Doc = Doc()
    initial_text = initial_doc.get("markdown", type=Text)
    initial_text += "Initial content"
    initial_update = initial_doc.get_update()

    shared_doc = await _create_shared_document(topic, initial_update)

    try:
        initial_count = await LiveDocumentUpdate.filter(topic_name=topic.name).count()

        other_instance_doc: Doc = Doc()
        other_instance_doc.apply_update(initial_update)
        other_text = other_instance_doc.get("markdown", type=Text)
        other_text += " plus new content"
        diff_update = other_instance_doc.get_update(initial_update)

        await shared_doc._handle_server_sync_update(_make_broadcast_payload(topic, diff_update))

        # Wait long enough for any async DB write task to complete.
        # The origin guard prevents the task from being spawned, but we need to
        # confirm no duplicate appears even with sufficient time for async work.
        for _ in range(50):
            await asyncio.sleep(0.01)

        final_count = await LiveDocumentUpdate.filter(topic_name=topic.name).count()
        assert final_count == initial_count, (
            f"Server sync update created {final_count - initial_count} new DB record(s). "
            f"Expected 0 — the originating instance already stored the update."
        )

        markdown = shared_doc.document.get("markdown", type=Text)
        assert str(markdown) == "Initial content plus new content"
    finally:
        await shared_doc.stop_session()


@pytest.mark.asyncio
async def test_client_sync_update_creates_db_record():
    """When a client sends a sync update (via handle_sync_message → observer),
    it should create exactly one LiveDocumentUpdate record.
    """
    topic = Topic("test_document", document_id=str(uuid4()))

    initial_doc: Doc = Doc()
    initial_text = initial_doc.get("markdown", type=Text)
    initial_text += "Initial content"
    initial_update = initial_doc.get_update()

    shared_doc = await _create_shared_document(topic, initial_update)

    try:
        initial_count = await LiveDocumentUpdate.filter(topic_name=topic.name).count()

        # Simulate a client edit: create an update as if typed by a user
        client_doc: Doc = Doc()
        client_doc.apply_update(initial_update)
        client_text = client_doc.get("markdown", type=Text)
        client_text += " plus client edit"
        diff_update = client_doc.get_update(initial_update)

        # Apply the update directly to the shared document (no origin = client/local)
        # This simulates what handle_sync_message does for SYNC_UPDATE messages
        shared_doc.document.apply_update(diff_update)

        # Wait for the observer task to persist the update
        for _ in range(50):
            final_count = await LiveDocumentUpdate.filter(topic_name=topic.name).count()
            if final_count > initial_count:
                break
            await asyncio.sleep(0.01)

        assert final_count == initial_count + 1, (
            f"Expected exactly 1 new DB record from client update, got {final_count - initial_count}."
        )

        markdown = shared_doc.document.get("markdown", type=Text)
        assert str(markdown) == "Initial content plus client edit"
    finally:
        await shared_doc.stop_session()
