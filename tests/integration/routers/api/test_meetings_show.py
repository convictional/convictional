from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import status

from app.jobs.content import IndexMeetingJob
from app.models.workspaces.meetings import (
    Meeting,
    MeetingAttendee,
    MeetingChatMessage,
    MeetingChatMessageSender,
    Transcript,
    TranscriptLine,
)
from config.enums import EventAction, MeetingAttendeeStatus, Sharing
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_file_reference,
    create_meeting,
    create_meeting_collection,
    create_organization,
    create_user,
)


async def _past_meeting_for_user(client: AppClient, **overrides) -> Meeting:
    user = await client.get_default_user()
    scheduled_at = datetime.now(UTC) - timedelta(days=1)
    defaults = {
        "title": "Past meeting",
        "scheduled_at": scheduled_at,
        "scheduled_end_at": scheduled_at + timedelta(hours=1),
        "creator_id": user.id,
        "organization_id": user.organization_id,
    }
    return await create_meeting(**{**defaults, **overrides})


@pytest.mark.asyncio
async def test_show_returns_full_field_shape(client: AppClient):
    meeting = await _past_meeting_for_user(
        client,
        title="Q1 Review",
        summary="Reviewed Q1 metrics",
        agenda="* Topic A\n* Topic B",
        sharing=Sharing.ORGANIZATION,
    )

    response = await client.get(f"/api/meetings/{meeting.id}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["id"] == str(meeting.id)
    assert data["title"] == "Q1 Review"
    assert data["summary"] == "Reviewed Q1 metrics"
    assert data["sharing"] == Sharing.ORGANIZATION.value
    assert data["is_completed"] is True
    assert data["is_upcoming"] is False
    assert data["is_recurring"] is False
    assert data["is_initial_processing"] is False
    assert data["did_recording_fail"] is False
    assert data["has_transcript"] is False
    assert data["has_chat_messages"] is False
    assert data["workspace_id"] == str(meeting.workspace_id)
    assert data["source_url"] == f"/meetings/{meeting.id}"
    assert data["recording_id"] is None
    assert data["conferencing_url"] is None
    assert data["collection"] is None
    assert data["previous_meeting_id"] is None
    assert data["next_meeting_id"] is None


@pytest.mark.asyncio
async def test_show_reflects_transcript_presence_and_recording_failure(client: AppClient):
    # The island gates its processing vs. ready vs. failed states on these two
    # flags, so they must reflect the underlying meeting state.
    with_transcript = await _past_meeting_for_user(client, transcript="Alice: hello\nBob: hi")
    failed = await _past_meeting_for_user(client, did_recording_fail=True)

    ready = (await client.get(f"/api/meetings/{with_transcript.id}")).json()
    assert ready["has_transcript"] is True
    assert ready["did_recording_fail"] is False

    failed_data = (await client.get(f"/api/meetings/{failed.id}")).json()
    assert failed_data["has_transcript"] is False
    assert failed_data["did_recording_fail"] is True


@pytest.mark.asyncio
async def test_show_returns_conferencing_url(client: AppClient):
    meeting = await _past_meeting_for_user(
        client,
        conferencing_url="https://zoom.us/j/1234567890",
    )

    response = await client.get(f"/api/meetings/{meeting.id}")
    data = response.json()
    assert data["conferencing_url"] == "https://zoom.us/j/1234567890"


@pytest.mark.asyncio
async def test_show_returns_404_for_cross_org_meeting(client: AppClient):
    other_org = await create_organization()
    other_creator = await create_user(organization_id=other_org.id)
    meeting = await create_meeting(
        creator_id=other_creator.id,
        organization_id=other_org.id,
        scheduled_at=datetime.now(UTC) - timedelta(days=1),
    )

    response = await client.get(f"/api/meetings/{meeting.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_show_recurring_links_set_when_recurring(client: AppClient):
    user = await client.get_default_user()
    provider_meeting_id = "provider-recurring-meeting-1"
    base = datetime.now(UTC) - timedelta(days=10)
    previous = await create_meeting(
        title="Earlier",
        creator_id=user.id,
        organization_id=user.organization_id,
        provider_meeting_id=provider_meeting_id,
        scheduled_at=base,
        scheduled_end_at=base + timedelta(hours=1),
    )
    current = await create_meeting(
        title="Current",
        creator_id=user.id,
        organization_id=user.organization_id,
        provider_meeting_id=provider_meeting_id,
        scheduled_at=base + timedelta(days=7),
        scheduled_end_at=base + timedelta(days=7, hours=1),
    )
    upcoming = await create_meeting(
        title="Later",
        creator_id=user.id,
        organization_id=user.organization_id,
        provider_meeting_id=provider_meeting_id,
        scheduled_at=base + timedelta(days=14),
        scheduled_end_at=base + timedelta(days=14, hours=1),
    )
    # Refresh so count_occurrences (set via post_save signal) is reflected
    for m in (previous, current, upcoming):
        await m.refresh_from_db()

    response = await client.get(f"/api/meetings/{current.id}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["is_recurring"] is True
    assert data["previous_meeting_id"] == str(previous.id)
    # get_next_meeting excludes future-only meetings, so the next link is null
    # because the later instance hasn't started yet.
    assert data["next_meeting_id"] is None


@pytest.mark.asyncio
async def test_show_collection_includes_auto_assigned_flag(client: AppClient):
    user = await client.get_default_user()
    collection = await create_meeting_collection(organization_id=user.organization_id, title="Standups")
    meeting = await _past_meeting_for_user(
        client,
        collection_id=collection.id,
        collection_auto_assigned=True,
    )

    response = await client.get(f"/api/meetings/{meeting.id}")
    data = response.json()
    assert data["collection"] == {
        "id": str(collection.id),
        "title": "Standups",
        "auto_assigned": True,
    }


@pytest.mark.asyncio
async def test_show_splits_user_and_unresolved_attendees(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    meeting = await _past_meeting_for_user(
        client,
        attendees=[
            MeetingAttendee(user_id=other_user.id, name=other_user.display_name),
            MeetingAttendee(name="External Guest", status=MeetingAttendeeStatus.ACCEPTED),
        ],
    )

    response = await client.get(f"/api/meetings/{meeting.id}")
    data = response.json()

    assert len(data["user_attendees"]) == 1
    assert data["user_attendees"][0]["id"] == str(other_user.id)
    assert data["unresolved_attendees"] == [
        {"display_name": "External Guest", "status": MeetingAttendeeStatus.ACCEPTED.value},
    ]


@pytest.mark.asyncio
async def test_show_counts_attendee_with_unresolvable_user_id(client: AppClient):
    # An attendee whose user_id doesn't resolve to a same-org User (here a
    # cross-org user; a deleted user behaves the same) must still be counted and
    # named via its embedded display_name, not silently dropped.
    cross_org_user = await create_user()
    meeting = await _past_meeting_for_user(
        client,
        attendees=[MeetingAttendee(user_id=cross_org_user.id, name="Cross Org Person")],
    )

    response = await client.get(f"/api/meetings/{meeting.id}")
    data = response.json()

    assert data["user_attendees"] == []
    assert data["unresolved_attendees"] == [
        {"display_name": "Cross Org Person", "status": None},
    ]


@pytest.mark.asyncio
async def test_recording_upload_url_returns_signed_target(client: AppClient, stub_content_indexing: None):
    meeting = await _past_meeting_for_user(client)

    response = await client.post(f"/api/meetings/{meeting.id}/recording/upload_url")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Local storage in tests yields a same-origin upload endpoint and empty
    # fields; what matters is the client gets an action, a fields map, and the
    # object key to echo back via PATCH recording_key.
    assert data["action"]
    assert isinstance(data["fields"], dict)
    assert data["key"]


@pytest.mark.asyncio
async def test_recording_endpoint_returns_resource_when_present(client: AppClient):
    file_ref = await create_file_reference()
    meeting = await _past_meeting_for_user(client)
    meeting.recording_id = file_ref.id
    await meeting.save()

    response = await client.get(f"/api/meetings/{meeting.id}/recording")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(file_ref.id)
    assert isinstance(data["url"], str)
    assert data["url"]


@pytest.mark.asyncio
async def test_recording_endpoint_returns_404_when_absent(client: AppClient):
    meeting = await _past_meeting_for_user(client)
    response = await client.get(f"/api/meetings/{meeting.id}/recording")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_transcript_endpoint_returns_lines_when_present(client: AppClient):
    transcript = Transcript(
        lines=[
            TranscriptLine(line_number=0, speaker="Dave", content="Hello", start_time=0.0, end_time=1.5),
            TranscriptLine(line_number=1, speaker="Alex", content="Hi back", start_time=1.5, end_time=2.7),
        ]
    )
    meeting = await _past_meeting_for_user(client, processed_transcript=transcript)

    response = await client.get(f"/api/meetings/{meeting.id}/transcript")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["lines"][0] == {
        "line_number": 0,
        "speaker": "Dave",
        "content": "Hello",
        "start_time": 0.0,
        "end_time": 1.5,
    }
    assert len(data["lines"]) == 2


@pytest.mark.asyncio
async def test_transcript_endpoint_returns_404_when_absent(client: AppClient):
    meeting = await _past_meeting_for_user(client)
    response = await client.get(f"/api/meetings/{meeting.id}/transcript")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_transcript_endpoint_returns_404_for_cross_org_meeting(client: AppClient):
    other_org = await create_organization()
    other_creator = await create_user(organization_id=other_org.id)
    meeting = await create_meeting(
        creator_id=other_creator.id,
        organization_id=other_org.id,
        scheduled_at=datetime.now(UTC) - timedelta(days=1),
        processed_transcript=Transcript(
            lines=[TranscriptLine(line_number=0, speaker="x", content="y", start_time=0.0, end_time=1.0)]
        ),
    )

    response = await client.get(f"/api/meetings/{meeting.id}/transcript")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_chat_endpoint_returns_messages_sorted_by_created_at(client: AppClient):
    meeting = await _past_meeting_for_user(
        client,
        chat_messages=[
            MeetingChatMessage(
                text="second",
                created_at=datetime(2026, 1, 1, 12, 5, tzinfo=UTC),
                to="everyone",
                sender=MeetingChatMessageSender(name="Alex"),
            ),
            MeetingChatMessage(
                text="first",
                created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
                to="everyone",
                sender=MeetingChatMessageSender(name="Dave"),
            ),
        ],
    )

    response = await client.get(f"/api/meetings/{meeting.id}/chat")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert [m["text"] for m in data["messages"]] == ["first", "second"]
    assert data["messages"][0]["sender_name"] == "Dave"
    assert data["messages"][0]["created_at"].startswith("2026-01-01T12:00")
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_chat_endpoint_returns_empty_list_when_absent(client: AppClient):
    meeting = await _past_meeting_for_user(client)
    response = await client.get(f"/api/meetings/{meeting.id}/chat")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["messages"] == []


@pytest.mark.asyncio
async def test_chat_endpoint_returns_404_for_cross_org_meeting(client: AppClient):
    other_org = await create_organization()
    other_creator = await create_user(organization_id=other_org.id)
    meeting = await create_meeting(
        creator_id=other_creator.id,
        organization_id=other_org.id,
        scheduled_at=datetime.now(UTC) - timedelta(days=1),
    )

    response = await client.get(f"/api/meetings/{meeting.id}/chat")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_patch_updates_title_summary_agenda_scheduled_at(client: AppClient):
    meeting = await _past_meeting_for_user(client, title="Old", summary="Old summary")
    new_time = (datetime.now(UTC) - timedelta(hours=5)).replace(microsecond=0)

    response = await client.patch(
        f"/api/meetings/{meeting.id}",
        json={
            "title": "New title",
            "summary": "New summary",
            "agenda": "* updated item",
            "scheduled_at": new_time.isoformat(),
        },
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["title"] == "New title"
    assert data["summary"] == "New summary"

    await meeting.refresh_from_db()
    assert meeting.title == "New title"
    assert meeting.summary == "New summary"
    assert meeting.agenda == "* updated item"
    assert meeting.scheduled_at == new_time

    await meeting.fetch_related("workspace__events")
    assert EventAction.MEETING_UPDATED in [e.action for e in meeting.workspace.events]


@pytest.mark.asyncio
async def test_patch_updates_sharing(client: AppClient):
    # Bare meeting (no transcript/agenda content) so the sharing change doesn't
    # trigger content re-indexing / embeddings.
    user = await client.get_default_user()
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)
    assert meeting.sharing == Sharing.PRIVATE

    response = await client.patch(
        f"/api/meetings/{meeting.id}",
        json={"sharing": Sharing.ORGANIZATION.value},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["sharing"] == Sharing.ORGANIZATION.value

    await meeting.refresh_from_db()
    assert meeting.sharing == Sharing.ORGANIZATION
    # The pre_save signal mirrors sharing onto the workspace row for querying.
    await meeting.workspace.refresh_from_db()
    assert meeting.workspace.sharing == Sharing.ORGANIZATION


@pytest.mark.asyncio
async def test_patch_clear_scheduled_at(client: AppClient):
    meeting = await _past_meeting_for_user(client)

    response = await client.patch(f"/api/meetings/{meeting.id}", json={"scheduled_at": None})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["scheduled_at"] is None

    await meeting.refresh_from_db()
    assert meeting.scheduled_at is None


@pytest.mark.asyncio
async def test_patch_collection_assign_fans_out_but_unassign_does_not(client: AppClient):
    """Pins the asymmetric recurring-series behavior: assign propagates to siblings so a
    newly-categorized series stays coherent, but unassign only clears the single instance
    so callers can pull one occurrence out of a series without disturbing the rest.
    """
    user = await client.get_default_user()
    collection = await create_meeting_collection(organization_id=user.organization_id, title="Series")
    ical_uid = "recurring-uid-1"
    sibling = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        ical_uid=ical_uid,
        scheduled_at=datetime.now(UTC) - timedelta(days=2),
        scheduled_end_at=datetime.now(UTC) - timedelta(days=2) + timedelta(hours=1),
    )
    current = await _past_meeting_for_user(client, ical_uid=ical_uid)

    response = await client.patch(f"/api/meetings/{current.id}", json={"collection_id": str(collection.id)})
    assert response.status_code == status.HTTP_200_OK
    await sibling.refresh_from_db()
    assert sibling.collection_id == collection.id

    response = await client.patch(f"/api/meetings/{current.id}", json={"collection_id": None})
    assert response.status_code == status.HTTP_200_OK
    await sibling.refresh_from_db()
    assert sibling.collection_id == collection.id  # sibling stays in the series collection


@pytest.mark.asyncio
async def test_patch_assign_and_unassign_collection(client: AppClient):
    user = await client.get_default_user()
    collection = await create_meeting_collection(organization_id=user.organization_id, title="Reviews")
    meeting = await _past_meeting_for_user(client)

    response = await client.patch(
        f"/api/meetings/{meeting.id}",
        json={"collection_id": str(collection.id)},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["collection"]["id"] == str(collection.id)
    assert response.json()["collection"]["auto_assigned"] is False

    response = await client.patch(f"/api/meetings/{meeting.id}", json={"collection_id": None})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["collection"] is None
    await meeting.refresh_from_db()
    assert meeting.collection_id is None


@pytest.mark.asyncio
async def test_patch_invalid_collection_id_returns_404_without_persisting_other_fields(client: AppClient):
    """Pins that field updates + collection mutation share one transaction:
    a bad collection_id rejects the whole request, so the title doesn't get
    silently saved while the caller sees a 404.
    """
    meeting = await _past_meeting_for_user(client, title="Original")

    response = await client.patch(
        f"/api/meetings/{meeting.id}",
        json={"title": "Should not stick", "collection_id": str(uuid4())},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND

    await meeting.refresh_from_db()
    assert meeting.title == "Original"


@pytest.mark.asyncio
async def test_patch_cross_org_collection_id_returns_404(client: AppClient):
    other_org = await create_organization()
    collection = await create_meeting_collection(organization_id=other_org.id, title="Off-limits")
    meeting = await _past_meeting_for_user(client, title="Original")

    response = await client.patch(
        f"/api/meetings/{meeting.id}",
        json={"title": "Should not stick", "collection_id": str(collection.id)},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND

    await meeting.refresh_from_db()
    assert meeting.title == "Original"
    assert meeting.collection_id is None


@pytest.mark.asyncio
async def test_patch_returns_404_for_cross_org_meeting(client: AppClient):
    other_org = await create_organization()
    other_creator = await create_user(organization_id=other_org.id)
    meeting = await create_meeting(
        creator_id=other_creator.id,
        organization_id=other_org.id,
        scheduled_at=datetime.now(UTC) - timedelta(days=1),
    )

    response = await client.patch(f"/api/meetings/{meeting.id}", json={"title": "Hijacked"})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.fixture
def stub_content_indexing(monkeypatch: pytest.MonkeyPatch):
    # PATCHing a meeting fans out to IndexMeetingJob, which hits OpenAI
    # embeddings. The other PATCH tests in this file are cassette-backed; the
    # recording_key tests don't need to record that fan-out to verify the
    # API contract.
    async def noop(self):
        pass

    monkeypatch.setattr(IndexMeetingJob, "perform", noop)


@pytest.mark.asyncio
async def test_patch_recording_key_materializes_file_reference(client: AppClient, stub_content_indexing: None):
    meeting = await _past_meeting_for_user(client)
    file = await create_file_reference(content=b"fake video bytes", filename="rec.mp4", content_type="video/mp4")

    response = await client.patch(f"/api/meetings/{meeting.id}", json={"recording_key": file.key})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["recording_id"] is not None

    response = await client.get(f"/api/meetings/{meeting.id}/recording")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["url"]


@pytest.mark.asyncio
async def test_patch_recording_key_rejects_empty_upload(client: AppClient, stub_content_indexing: None):
    meeting = await _past_meeting_for_user(client, title="Original")
    file = await create_file_reference(content=b"", filename="empty.mp4", content_type="video/mp4")

    response = await client.patch(
        f"/api/meetings/{meeting.id}",
        json={"title": "Should not apply", "recording_key": file.key},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    refreshed = await Meeting.get(id=meeting.id)
    assert refreshed.title == "Original"
    assert refreshed.recording_id is None


@pytest.mark.asyncio
async def test_delete_returns_204_for_past_meeting(client: AppClient):
    meeting = await _past_meeting_for_user(client)

    response = await client.delete(f"/api/meetings/{meeting.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert await Meeting.get_or_none(id=meeting.id) is None

    await meeting.fetch_related("workspace__events")
    assert EventAction.MEETING_DELETED in [e.action for e in meeting.workspace.events]


@pytest.mark.asyncio
async def test_delete_returns_409_for_upcoming_meeting(client: AppClient):
    user = await client.get_default_user()
    upcoming = await create_meeting(
        title="Upcoming",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=datetime.now(UTC) + timedelta(days=2),
        scheduled_end_at=datetime.now(UTC) + timedelta(days=2, hours=1),
    )

    response = await client.delete(f"/api/meetings/{upcoming.id}")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert await Meeting.get_or_none(id=upcoming.id) is not None


@pytest.mark.asyncio
async def test_delete_returns_404_for_cross_org_meeting(client: AppClient):
    other_org = await create_organization()
    other_creator = await create_user(organization_id=other_org.id)
    meeting = await create_meeting(
        creator_id=other_creator.id,
        organization_id=other_org.id,
        scheduled_at=datetime.now(UTC) - timedelta(days=1),
    )

    response = await client.delete(f"/api/meetings/{meeting.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
