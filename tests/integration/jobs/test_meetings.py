from uuid import UUID

import pytest

from app.jobs.meetings import (
    AssignMeetingCollectionJob,
    MeetingProcessingCompleteCallbackJob,
    ProcessTranscriptJob,
)
from app.models.accounts import EmailAlias, User
from app.models.collaboration.workspace import Event
from app.models.workspaces.meetings import Meeting, MeetingCollection
from config.enums import EventAction, MeetingAttendeeStatus
from infra.jobs import JobsOutbox, enqueue_job_group
from integrations.recall_ai.models import RecallAICalendarAttendee
from tests.helpers.factories import (
    create_meeting,
    create_meeting_collection,
    create_organization,
    create_user,
)

pytestmark = pytest.mark.real_embeddings

with open("tests/fixtures/test_meeting_summary_transcript.txt") as f:
    agenda_transcript = f.read()

with open("tests/fixtures/test_meeting_summary_agenda.txt") as f:
    agenda = f.read()

with open("tests/fixtures/meeting_decision_extraction_transcript.txt") as f:
    action_item_transcript = f.read()

with open("tests/fixtures/meeting_external_party_decision_transcript.txt") as f:
    external_party_transcript = f.read()


def decisions_section(summary: str) -> str:
    """Return the body of the '### Decisions' section of a summary, or '' if it was omitted."""
    body: list[str] = []
    capturing = False
    for line in summary.splitlines():
        if line.strip().startswith("### "):
            capturing = line.strip() == "### Decisions"
            continue
        if capturing:
            body.append(line)
    return "\n".join(body).strip()


async def extract_meeting(transcript: str, internal_member_names: list[str]) -> Meeting:
    """Run the real extraction pipeline over a transcript and return the saved meeting.

    Internal members are created as org users so resolve_attendees links them to the matching
    speakers — this drives meeting.is_internal and, with at least one unresolved (external)
    speaker, the "external party" branch of the decisions prompt. Speaker names must match exactly.

    LLM output is recorded via VCR. After editing the prompt, re-run with --record-mode=rewrite
    so the model is hit again (cassettes match on URL, not body, and otherwise replay stale output).
    """
    organization = await create_organization()
    members = [await create_user(organization_id=organization.id, name=name) for name in internal_member_names]

    meeting = await Meeting.create(
        title="Meeting",
        transcript=transcript,
        organization_id=organization.id,
        creator_id=members[0].id,
    )

    async with JobsOutbox():
        await ProcessTranscriptJob(meeting_id=meeting.id, should_update_title=True).perform()

    await meeting.refresh_from_db()
    return meeting


@pytest.mark.asyncio
async def test_meeting_agenda_summary():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    # Create a meeting with the transcript and agenda
    meeting = await Meeting.create(
        title="Meeting",
        transcript=agenda_transcript,
        agenda=agenda,
        organization_id=organization.id,
        creator_id=user.id,
    )
    async with JobsOutbox():
        await ProcessTranscriptJob(meeting_id=meeting.id, should_update_title=True).perform()

    await meeting.refresh_from_db()
    assert meeting.processed_transcript
    assert meeting.summary

    assert "Agenda Review" in meeting.summary
    assert "Missed Topics" in meeting.summary

    # Assert on the heading marker, not the bare word "Decisions" — the agenda fixture
    # contains the phrase "Open Decisions + Discussion Topics", which would false-positive.
    assert "### Decisions" in meeting.summary

    # Create a meeting without an agenda
    meeting = await Meeting.create(
        title="Meeting", transcript=agenda_transcript, organization_id=organization.id, creator_id=user.id
    )

    async with JobsOutbox():
        await ProcessTranscriptJob(meeting_id=meeting.id, should_update_title=True).perform()

    await meeting.refresh_from_db()
    assert meeting.processed_transcript
    assert meeting.summary

    assert "Agenda Review" not in meeting.summary
    assert "Missed Topics" not in meeting.summary


@pytest.mark.asyncio
async def test_meeting_decision_extraction_excludes_action_items():
    # Piotr Kaminski is the external prospect; the rest are Convictional members.
    meeting = await extract_meeting(action_item_transcript, ["Elena Marchetti", "Theo Nakamura", "Simone Aubert"])
    assert meeting.summary

    # Sanity-check the external-party branch is active: Piotr is the unresolved (external) attendee.
    assert not meeting.is_internal

    decisions = decisions_section(meeting.summary)
    assert "demo" not in decisions.lower(), f"Custom-demo action item was extracted as a decision:\n{decisions}"
    assert decisions == "", f"Expected no decisions for this meeting, but got:\n{decisions}"


@pytest.mark.asyncio
async def test_meeting_decision_extraction_excludes_external_party_decisions():
    # Wilfred Osei is the external prospect; the rest are Convictional members.
    meeting = await extract_meeting(external_party_transcript, ["Elena Marchetti", "Theo Nakamura", "Rosa Beltran"])
    assert meeting.summary

    assert not meeting.is_internal

    # This demo call contains no decision the org made. The model tends to over-extract one of two
    # non-decisions here: the prospect's own choice to add their team as users (an outside party's
    # affair) or "Rosa will explore importing their ClickUp data" (a tentative action item). Both
    # are already excluded by the prompt rules, so the section should be omitted entirely.
    decisions = decisions_section(meeting.summary)
    assert decisions == "", f"Expected no decisions for this demo meeting, but got:\n{decisions}"


@pytest.mark.asyncio
async def test_meeting_job_callback():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    # Create a meeting with the transcript and agenda
    meeting = await Meeting.create(
        title="Meeting",
        transcript="Transcript",
        organization_id=organization.id,
        creator_id=user.id,
    )

    job_def = MeetingProcessingCompleteCallbackJob(meeting_id=meeting.id)

    # Notification should not be sent if the meeting is not processed
    await job_def.perform()
    events = await Event.all()
    assert len(events) == 0

    # When run as a group callback, the notification will be sent
    async with JobsOutbox():
        await enqueue_job_group([ProcessTranscriptJob(meeting_id=meeting.id)], job_def)

    events = await Event.all()
    assert len(events) == 1
    assert events[0].action == EventAction.MEETING_PROCESSED


@pytest.mark.asyncio
async def test_resolve_attendee_by_email_alias():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id, email="primary@example.com", name="Test User")
    alias_email = "secondary@example.com"
    await EmailAlias.create(address=alias_email, user_id=user.id)
    attendee = RecallAICalendarAttendee(
        name="Test User", email=alias_email, is_organizer=True, status=MeetingAttendeeStatus.ACCEPTED
    )

    # Get users by email aliases (simulating what happens in the job)
    users = await User.filter(
        User.filters.by_any_email([alias_email, "foo@bar.com"]) & User.filters.by_organization(organization.id)
    ).prefetch_related("email_aliases")
    meeting_attendee = attendee.as_meeting_attendee(users)

    # user was correctly resolved through the email alias
    assert meeting_attendee.user_id == user.id
    assert meeting_attendee.name == user.display_name
    assert meeting_attendee.is_organizer is True
    assert meeting_attendee.status == MeetingAttendeeStatus.ACCEPTED


@pytest.mark.asyncio
async def test_assign_meeting_collection_skips_when_collection_assigned():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    collection = await create_meeting_collection(organization_id=organization.id)
    meeting = await create_meeting(organization_id=organization.id, creator_id=user.id, collection_id=collection.id)

    job = AssignMeetingCollectionJob(meeting_id=meeting.id)
    await job.perform()

    await meeting.refresh_from_db()
    assert meeting.collection_id == collection.id
    assert meeting.collection_auto_assigned is False


@pytest.mark.asyncio
async def test_assign_meeting_collection_assigns_existing():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    # ID must match the VCR cassette response — re-record if this changes
    collection = await create_meeting_collection(
        id=UUID("4c0bd591-dcaa-4880-a851-7cb985e240d0"),
        organization_id=organization.id,
        title="Daily Standups",
    )
    meeting = await create_meeting(organization_id=organization.id, creator_id=user.id)

    job = AssignMeetingCollectionJob(meeting_id=meeting.id)
    await job.perform()

    await meeting.refresh_from_db()
    assert meeting.collection_id == collection.id
    assert meeting.collection_auto_assigned is True


@pytest.mark.asyncio
async def test_assign_meeting_collection_creates_and_assigns_new():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    meeting = await create_meeting(
        organization_id=organization.id,
        creator_id=user.id,
        title="Q4 Board Meeting",
        summary="Quarterly review of company financials and strategy with the board of directors.",
    )

    job = AssignMeetingCollectionJob(meeting_id=meeting.id)
    await job.perform()

    await meeting.refresh_from_db()
    assert meeting.collection_id is not None
    assert meeting.collection_auto_assigned is True

    collection = await MeetingCollection.get(id=meeting.collection_id)
    assert collection.title == "Board Meetings"
    assert collection.organization_id == organization.id


@pytest.mark.asyncio
async def test_assign_meeting_collection_handles_none():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    await create_meeting_collection(organization_id=organization.id, title="Engineering Standups")
    await create_meeting_collection(
        organization_id=organization.id, title="Sales Pipeline Reviews", description="Weekly sales pipeline reviews"
    )
    meeting = await create_meeting(
        organization_id=organization.id,
        creator_id=user.id,
        title="Going Away Party for Steve",
        summary="Planning Steve's farewell party next Friday. Discussed venue, food, and gift ideas.",
    )

    job = AssignMeetingCollectionJob(meeting_id=meeting.id)
    await job.perform()

    await meeting.refresh_from_db()
    assert meeting.collection_id is None
    assert meeting.collection_auto_assigned is False
