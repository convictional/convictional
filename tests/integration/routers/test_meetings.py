from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import status

from app.jobs.meetings import ExtractMeetingMetadataJob, ProcessTranscriptJob
from app.models.accounts import User
from app.models.collaboration.content import Content
from app.models.collaboration.workspace import Collaborator, SubscriptionPreference
from app.models.workspaces.meetings import (
    Meeting,
    MeetingAttendee,
    MeetingChatMessage,
    MeetingChatMessageSender,
)
from app.presenters.meeting import MeetingPresenter
from config import settings
from config.enums import ContentType, EventAction, Sharing, SubscriptionLevel
from infra.email import FakeDelivery
from infra.jobs import InlineJobs
from integrations.recall_ai.jobs import ScheduleRecallAIBotJob
from integrations.recall_ai.models import (
    RecallAIBotStatusCodes,
    RecallAIMeeting,
    RecallAIPlatform,
)
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_meeting,
    create_meeting_collection,
    create_organization,
    create_user,
)

sample_transcript = """Tom Wilson: Good morning everyone, and thanks for joining our weekly project sync. Today we'll be focusing on the Q4 campaign launch progress and addressing any roadblocks. Sarah, would you like to kick us off with the marketing updates?
Sarah Chen: Thanks, Tom. I've reviewed the latest analytics from our test campaign, and we're seeing some promising results. Click-through rates are averaging 3.2%, which is about 0.8% higher than our previous campaigns. This brings me to our main decision point today – how we want to handle our ad spend allocation.
Maya Patel: What are our options looking like?
Sarah Chen: We essentially have two paths forward. We could go broad with a larger audience and lower cost per impression across all platforms, or we could focus heavily on Instagram and LinkedIn where we're seeing the highest engagement rates, but that means a higher cost per impression.
James Rodriguez: The engagement numbers on those platforms are impressive, but wouldn't we be missing out on the TikTok demographic entirely?
Maya Patel: True, but our conversion rates on Instagram are nearly double what we're seeing on TikTok. Plus, the lead quality from LinkedIn has been consistently higher.
Tom Wilson: Let's break this down. What's our priority here – reach or conversion quality?
Sarah Chen: Looking at the Q4 targets, we need a 15% increase in qualified leads more than we need raw awareness. Given our budget constraints and these engagement metrics, I recommend we concentrate on Instagram and LinkedIn.
James Rodriguez: That makes sense. We can also repurpose our high-performing creative assets for these platforms, which would save us some production costs.
Sarah Chen: Exactly, and we're covering the criteria for both reach and quality. I'll adjust the media plan accordingly.
Tom Wilson: Alright, let's make this official. We'll reallocate the budget to focus on Instagram and LinkedIn. Sarah, can you adjust the media plan accordingly?
Sarah Chen: Will do. I'll have the revised plan by Wednesday.
Tom Wilson: Great. Moving on to other updates – James, how are we looking on the creative side?
James Rodriguez: Good. We've finalized the visual assets for the main campaign. Maya, I've shared those with you for the social media rollout. One concern though – we might need to adjust some of the color schemes for better accessibility.
Maya Patel: Got it, James. I'll start adapting these for our focused platform strategy.
Tom Wilson: Alright, let's wrap this up. Action items for everyone:

Sarah - Send revised media plan by Wednesday
James - Revise color schemes for accessibility
Maya - Adapt content calendar for Instagram and LinkedIn focus
Everyone - Update project timelines by EOD

Any final questions or concerns?
Sarah Chen: All clear on my end.
James Rodriguez: Nothing from me.
Maya Patel: We're good.
Tom Wilson: Great work, everyone. Next meeting same time next week. Thanks for your time.
"""  # noqa: E501


@pytest.mark.real_embeddings
@pytest.mark.asyncio
async def test_meetings_metadata_extraction(client: AppClient):
    user = await client.get_default_user()

    response = await client.post(
        "/api/meetings",
        json={"type": "transcript", "transcript": sample_transcript, "sharing": Sharing.ORGANIZATION.value},
    )
    assert response.status_code == status.HTTP_201_CREATED

    meeting_id = UUID(response.json()["id"])

    created_meeting = await Meeting.get(id=meeting_id).prefetch_related("workspace__events")

    assert created_meeting.organization_id == user.organization_id
    assert created_meeting.creator_id == user.id
    assert len(created_meeting.title) > 0
    assert len(created_meeting.attendees) == 4
    assert MeetingAttendee(name="Sarah Chen") in created_meeting.attendees
    assert MeetingAttendee(name="Maya Patel") in created_meeting.attendees
    assert MeetingAttendee(name="James Rodriguez") in created_meeting.attendees
    assert MeetingAttendee(name="Tom Wilson") in created_meeting.attendees
    assert created_meeting.summary is not None
    event_actions = [event.action for event in created_meeting.workspace.events]
    assert EventAction.MEETING_PROCESSED in event_actions

    assert await Content.all().count() == 2
    meeting_summary_content = await Content.get(source_id=created_meeting.global_id)
    assert meeting_summary_content is not None
    assert meeting_summary_content.content_type == ContentType.MEETING
    assert meeting_summary_content.title is not None
    assert meeting_summary_content.index_content is not None

    meeting_transcript_content = await Content.get(source_id__startswith=f"{created_meeting.global_id}#timestamp")
    assert meeting_transcript_content is not None
    assert meeting_transcript_content.content_type == ContentType.MEETING_TRANSCRIPT
    assert meeting_transcript_content.title is not None
    assert meeting_transcript_content.index_content is not None


@pytest.mark.real_embeddings
@pytest.mark.asyncio
async def test_meetings_process_transcript(client: AppClient, background_jobs: InlineJobs):
    response = await client.post("/api/meetings", json={"type": "transcript", "transcript": sample_transcript})
    assert response.status_code == status.HTTP_201_CREATED

    # Metadata extraction was queued
    assert any(isinstance(job.job_definition, ProcessTranscriptJob) for job in background_jobs.completed)
    assert any(isinstance(job.job_definition, ExtractMeetingMetadataJob) for job in background_jobs.completed)


@pytest.mark.real_embeddings
@pytest.mark.asyncio
async def test_fathom_meeting_processing(client: AppClient, background_jobs: InlineJobs):
    with open(settings.root / "tests" / "fixtures" / "fathom-2.txt") as f:
        transcript = f.read()

    response = await client.post("/api/meetings", json={"type": "transcript", "transcript": transcript})
    assert response.status_code == status.HTTP_201_CREATED
    meeting_id = UUID(response.json()["id"])

    # Metadata extraction was queued
    assert any(isinstance(job.job_definition, ProcessTranscriptJob) for job in background_jobs.completed)
    assert any(isinstance(job.job_definition, ExtractMeetingMetadataJob) for job in background_jobs.completed)

    # Meeting was updated with metadata from the transcript
    meeting = await Meeting.get(id=meeting_id)
    assert meeting.title == "Rina"
    assert meeting.scheduled_at
    assert meeting.scheduled_at.month == 12
    assert meeting.scheduled_at.day == 3


@pytest.mark.asyncio
async def test_meetings_index(client: AppClient):
    # The page hosts the unified meetings-list island across all three modes:
    # Most Recent (default), Uncategorized, and a specific collection.
    response = await client.get("/meetings")
    assert response.status_code == status.HTTP_200_OK
    assert 'id="react-meetings-index"' in response.text

    response = await client.get("/meetings?filter=uncategorized")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_meetings_index_collection_filter(client: AppClient):
    user = await client.get_default_user()
    collection = await create_meeting_collection(organization_id=user.organization_id)

    response = await client.get(f"/meetings?collection_id={collection.id}")
    assert response.status_code == status.HTTP_200_OK
    assert 'id="react-meetings-index"' in response.text


@pytest.mark.asyncio
async def test_meetings_index_collection_filter_404s_for_unknown_or_cross_org(client: AppClient):
    other_org = await create_organization()
    other_collection = await create_meeting_collection(organization_id=other_org.id)

    unknown = await client.get(f"/meetings?collection_id={uuid4()}")
    assert unknown.status_code == status.HTTP_404_NOT_FOUND

    cross_org = await client.get(f"/meetings?collection_id={other_collection.id}")
    assert cross_org.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_meetings_collection_show_redirects_to_filtered_index(client: AppClient):
    # The collection-show page folded into /meetings. Existing bookmarks and
    # email links must redirect to the filtered list, preserving the id.
    user = await client.get_default_user()
    collection = await create_meeting_collection(organization_id=user.organization_id)

    response = await client.get(f"/meetings_collections/{collection.id}", follow_redirects=False)
    assert response.status_code == status.HTTP_301_MOVED_PERMANENTLY
    assert response.headers["location"].endswith(f"/meetings?collection_id={collection.id}")


@pytest.mark.asyncio
async def test_meetings_show(client: AppClient):
    user = await client.get_default_user()

    meeting = await create_meeting(
        title="Test meeting",
        scheduled_at=datetime.now(UTC),
        attendees=[MeetingAttendee(name="Dave")],
        summary="Summary",
        organization_id=user.organization_id,
        creator_id=user.id,
    )

    response = await client.get(f"/meetings/{meeting.id}")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_meetings_show_recording_failed(client: AppClient):
    user = await client.get_default_user()
    scheduled_at = datetime.now(UTC) - timedelta(days=1)

    meeting = await create_meeting(
        title="Failed recording meeting",
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
        organization_id=user.organization_id,
        creator_id=user.id,
        sharing=Sharing.ORGANIZATION,
    )

    meeting.did_recording_fail = True
    await meeting.save(update_fields=["did_recording_fail"])

    # A past meeting whose recording failed still serves the show page (no redirect
    # to the upcoming variant). The failed-recording UI is rendered by the React
    # island from the meetings + bot APIs — see MeetingShow.test.tsx.
    response = await client.get(f"/meetings/{meeting.id}")
    assert response.status_code == status.HTTP_200_OK
    assert 'id="react-meeting-show"' in response.text


@pytest.mark.asyncio
async def test_meetings_notifications(client: AppClient, email_delivery: FakeDelivery):
    user = await client.get_default_user()
    other_user = await create_user(email="other@example.com", name="Tom Wilson", organization_id=user.organization_id)
    unrelated_user = await create_user(
        email="other1@example.com", name="Charlie Day", organization_id=user.organization_id
    )
    await SubscriptionPreference.update_for(user.id, {Meeting.record_type: SubscriptionLevel.ALL})
    await SubscriptionPreference.update_for(other_user.id, {Meeting.record_type: SubscriptionLevel.ALL})

    response = await client.post("/api/meetings", json={"type": "transcript", "transcript": sample_transcript})
    assert response.status_code == status.HTTP_201_CREATED

    # The default user was notified because they uploaded the transcript
    user_emails = email_delivery.by_recipient(user.email)
    assert len(user_emails) == 1
    assert "Meeting" in user_emails[0].subject

    # The other user was notified because they were mentioned in the transcript
    other_user_emails = email_delivery.by_recipient(other_user.email)
    assert len(other_user_emails) == 1
    assert "Meeting" in other_user_emails[0].subject

    # The unrelated user was not notified
    unrelated_user_emails = email_delivery.by_recipient(unrelated_user.email)
    assert len(unrelated_user_emails) == 0


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_meeting_create_with_recall_ai_bot(client: AppClient, background_jobs: InlineJobs):
    # Note: When re-recording this test, you'll need an active Conferencing URL and
    # a valid Recall AI API key to run this test. See docs/integrations.md for more details.
    response = await client.post(
        "/api/meetings",
        json={
            "type": "url",
            "title": "Test Recall Bot",
            "scheduled_at": datetime.now(UTC).isoformat(),
            "conferencing_url": "https://meet.google.com/ebf-sucq-adc",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    assert background_jobs.has_completed_job(ScheduleRecallAIBotJob)

    meeting = await Meeting.first()
    assert meeting
    recall_ai_meeting = await RecallAIMeeting.get_or_none(meeting_id=meeting.id)
    assert recall_ai_meeting
    assert recall_ai_meeting.bot_id is not None

    # Test Scheduled bot

    response = await client.post(
        "/api/meetings",
        json={
            "type": "url",
            "title": "Test Scheduled Recall Bot",
            "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "conferencing_url": "https://meet.google.com/ebf-sucq-adc",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    assert len(background_jobs.completed) == 2
    assert background_jobs.has_completed_job(ScheduleRecallAIBotJob)

    meeting = await Meeting.get(title="Test Scheduled Recall Bot")
    assert meeting
    recall_ai_meeting = await RecallAIMeeting.get_or_none(meeting_id=meeting.id)
    assert recall_ai_meeting
    assert recall_ai_meeting.bot_id is not None


@pytest.mark.asyncio
async def test_webex_meeting_not_joinable(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()

    # Webex URLs are not in the recall_ai_providers list, so meeting.is_joinable_by_recall will be False
    meeting = await create_meeting(
        title="Webex Meeting",
        scheduled_at=datetime.now(UTC) + timedelta(hours=1),
        conferencing_url="https://convictional.webex.com/meet/test",
        organization_id=user.organization_id,
        creator_id=user.id,
    )

    # Verify the meeting is not joinable by RecallAI
    assert meeting.is_joinable_by_recall is False

    recall_ai_meeting = await RecallAIMeeting.create(meeting_id=meeting.id, meeting_platform=RecallAIPlatform.WEBEX)

    job = ScheduleRecallAIBotJob(meeting_id=meeting.id)
    await job.perform()

    # Job exits early since is_joinable_by_recall is False, so bot_status remains NONE
    await recall_ai_meeting.refresh_from_db()
    assert recall_ai_meeting.bot_id is None
    assert recall_ai_meeting.bot_status == RecallAIBotStatusCodes.NONE
    assert recall_ai_meeting.will_record is False


@pytest.mark.asyncio
async def test_meetings_permissions(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(email="other@example.com", organization_id=user.organization_id)

    # Create a meeting with default (Private) sharing
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)

    # User can view the meeting
    response = await client.get(f"/meetings/{meeting.id}")
    assert response.status_code == status.HTTP_200_OK

    # User can view their own list of meetings
    meetings = await Meeting.by_organization_or_user(organization_id=user.organization.id, user_id=user.id)
    assert len(meetings) == 1 and meetings[0].id == meeting.id

    # Other user cannot
    with client.current_user_as(other_user):
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK
        assert meeting.title not in response.text
        assert "Request access" in response.text

    # Meeting does not appear in other user's list
    meetings = await Meeting.by_organization_or_user(organization_id=user.organization.id, user_id=other_user.id)
    assert len(meetings) == 0

    # User updates the meeting to add the other as a collaborators
    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators", json={"user_id": str(other_user.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Assert no error if adding the same collaborator again
    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators", json={"user_id": str(other_user.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Other user can now view the meeting
    with client.current_user_as(other_user):
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK
    meetings = await Meeting.by_organization_or_user(organization_id=user.organization.id, user_id=other_user.id)
    assert len(meetings) == 1 and meetings[0].id == meeting.id

    # Create a meeting with Organization sharing
    meeting = await create_meeting(
        creator_id=user.id, organization_id=user.organization_id, sharing=Sharing.ORGANIZATION
    )

    # User can view the meeting
    response = await client.get(f"/meetings/{meeting.id}")
    assert response.status_code == status.HTTP_200_OK

    # Other user can view the meeting
    with client.current_user_as(other_user):
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK

    # Org-shared meeting appears when listing by organization
    meetings = await Meeting.by_organization_or_user(organization_id=user.organization_id, user_id=user.id)
    assert len(meetings) == 2


@pytest.mark.asyncio
async def test_meetings_request_access(client: AppClient, email_delivery: FakeDelivery):
    user = await client.get_default_user()
    other_user = await create_user(email="other@example.com", organization_id=user.organization_id)
    await SubscriptionPreference.update_for(user.id, {Meeting.record_type: SubscriptionLevel.ALL})
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)
    org_users = await User.active.get_queryset().filter(organization_id=user.organization_id)

    # Other user sees request access page
    with client.current_user_as(other_user):
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK
        assert "Request access" in response.text

        # Other user requests access
        response = await client.post(
            f"/api/workspaces/{meeting.workspace_id}/collaborators/access", json={"note": "Please let me in"}
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Other user sees pending access page
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK
        assert "Request access" in response.text

    # Pending collaborator is created
    collaborator = await Collaborator.unscoped.get_queryset().get(
        workspace_id=meeting.workspace_id, user_id=other_user.id
    )
    assert isinstance(collaborator, Collaborator)
    assert collaborator.status.is_pending

    # Email is sent to the meeting creator
    emails = email_delivery.by_recipient(user.email)
    assert len(emails) == 1

    # Meeting presenter includes pending collaborator (testing this via UI is impossible)
    await meeting.fetch_related("organization", "workspace__collaborators__user", "jobs", "jobs__job", "recording")
    presenter = await MeetingPresenter.create(meeting, user, org_users)
    assert presenter
    assert len(presenter.collaborators.pending) == 1

    # Meeting creator approves access
    response = await client.post(f"/api/workspaces/{meeting.workspace_id}/collaborators/{collaborator.id}/approve")
    assert response.status_code == status.HTTP_201_CREATED

    # Other user can now view the meeting
    with client.current_user_as(other_user):
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK
        assert "Request access" not in response.text
        assert meeting.title in response.text


@pytest.mark.asyncio
async def test_recurring_meeting_getters():
    organization = await create_organization()
    ical_uid = "ical_uid"
    provider_meeting_id = "provider-meeting-123"
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)
    meetings: list[Meeting] = [
        await create_meeting(
            title="Meeting 1",
            organization_id=organization.id,
            ical_uid=ical_uid,
            provider_meeting_id=provider_meeting_id,
            scheduled_at=two_days_ago,
            scheduled_end_at=two_days_ago + timedelta(hours=1),
        ),
        await create_meeting(
            title="Meeting 2",
            organization_id=organization.id,
            ical_uid=ical_uid,
            provider_meeting_id=provider_meeting_id,
            scheduled_at=yesterday,
            scheduled_end_at=yesterday + timedelta(hours=1),
        ),
        await create_meeting(
            title="In-progress Meeting",
            organization_id=organization.id,
            ical_uid=ical_uid,
            provider_meeting_id=provider_meeting_id,
            scheduled_at=now - timedelta(minutes=15),
            scheduled_end_at=now + timedelta(minutes=45),
        ),
        await create_meeting(
            title="Future Meeting",
            organization_id=organization.id,
            ical_uid=ical_uid,
            provider_meeting_id=provider_meeting_id,
            scheduled_at=now + timedelta(days=1),  # Future meetings are excluded from next_meeting
            scheduled_end_at=now + timedelta(days=1, hours=1),
        ),
    ]

    for meeting in meetings:
        await meeting.refresh_from_db()
        assert meeting.count_occurrences == len(meetings)
        assert meeting.is_recurring

    assert await meetings[0].get_previous_meeting() is None
    assert await meetings[0].get_next_meeting() == meetings[1]

    assert await meetings[1].get_previous_meeting() == meetings[0]
    assert await meetings[1].get_next_meeting() == meetings[2]

    assert await meetings[2].get_previous_meeting() == meetings[1]
    assert await meetings[2].get_next_meeting() is None


@pytest.mark.asyncio
async def test_meeting_between_two_orgs_is_not_recurring():
    organization_one = await create_organization()
    organization_two = await create_organization()
    ical_uid = "ical_uid"

    org_one_meeting = await create_meeting(
        title="Meeting between two orgs",
        organization_id=organization_one.id,
        ical_uid=ical_uid,
        scheduled_at=datetime.now(UTC),
        scheduled_end_at=datetime.now(UTC) + timedelta(hours=1),
    )
    org_two_meeting = await create_meeting(
        title="Meeting between two orgs",
        organization_id=organization_two.id,
        ical_uid=ical_uid,
        scheduled_at=datetime.now(UTC),
        scheduled_end_at=datetime.now(UTC) + timedelta(hours=1),
    )

    assert org_one_meeting.ical_uid == org_two_meeting.ical_uid
    assert org_one_meeting.organization_id != org_two_meeting.organization_id
    assert org_one_meeting.count_occurrences == 1
    assert org_two_meeting.count_occurrences == 1
    assert org_one_meeting.is_recurring is False
    assert org_two_meeting.is_recurring is False


@pytest.mark.asyncio
async def test_upcoming_meeting(client: AppClient, email_delivery: FakeDelivery):
    user = await client.get_default_user()
    another_user = await create_user(organization_id=user.organization_id)
    await SubscriptionPreference.update_for(another_user.id, {Meeting.record_type: SubscriptionLevel.ALL})

    meeting = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
        attendees=[MeetingAttendee(user_id=user.id), MeetingAttendee(user_id=another_user.id)],
    )

    with client.current_user_as(user):
        # A single show route serves every lifecycle state; the React island
        # picks the upcoming view from the meeting payload. The title still
        # renders server-side via the page <title> block.
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK
        assert meeting.title in response.text
        assert 'id="react-meeting-show"' in response.text

        response = await client.patch(f"/api/meetings/{meeting.id}", json={"agenda": "Test agenda"})
        assert response.status_code == status.HTTP_200_OK

    await meeting.refresh_from_db()
    assert meeting.agenda == "Test agenda"

    emails = email_delivery.by_recipient(another_user.email)
    assert len(emails) == 1
    assert meeting.title in emails[0].subject
    assert "Test agenda" in emails[0].text


@pytest.mark.asyncio
async def test_legacy_upcoming_route_redirects(client: AppClient):
    # The old /meetings/{id}/upcoming route is gone, but emails and bookmarks
    # still point at it, so it must redirect to the unified show page.
    user = await client.get_default_user()
    meeting = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
    )

    response = await client.get(f"/meetings/{meeting.id}/upcoming", follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"].endswith(f"/meetings/{meeting.id}")


@pytest.mark.asyncio
async def test_meeting_serialize_chat_message(client: AppClient):
    user = await client.get_default_user()

    meeting = await create_meeting(
        title="Test meeting",
        scheduled_at=datetime.now(UTC),
        attendees=[MeetingAttendee(name="Dave")],
        summary="Summary",
        organization_id=user.organization_id,
        creator_id=user.id,
    )

    chat_messages = [
        MeetingChatMessage(
            text="https://www.gumloop.com/",
            created_at=datetime(2025, 4, 9, 14, 27, 23, 757787, tzinfo=UTC),
            to="all",
            sender=MeetingChatMessageSender(
                id=12345,
                name="Dave",
            ),
        )
    ]

    meeting.chat_messages = chat_messages
    await meeting.save()
    await meeting.refresh_from_db()

    # Verify that the chat messages were saved and can be retrieved
    assert len(meeting.chat_messages) == 1
    assert meeting.chat_messages[0].text == "https://www.gumloop.com/"


@pytest.mark.asyncio
async def test_meetings_upcoming_page(client: AppClient):
    # The page shell hosts the React upcoming-meetings island; the meeting data
    # is served by GET /api/meetings (covered in test_meetings_list.py).
    response = await client.get("/meetings/upcoming")
    assert response.status_code == status.HTTP_200_OK
    assert 'id="react-meetings-upcoming-index"' in response.text
