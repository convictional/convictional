import pytest

from app.presenters.meeting import MeetingPresenter
from config.enums import MeetingAttendeeStatus
from integrations.recall_ai.models import RecallAICalendarAttendee
from tests.helpers.factories import create_meeting, create_organization, create_user


@pytest.mark.asyncio
async def test_meeting_presenter_creation():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    another_user = await create_user(email="another@example.com", organization_id=organization.id)
    meeting = await create_meeting(organization_id=organization.id, creator_id=user.id)
    attendee = RecallAICalendarAttendee(
        email=another_user.email, name="Another User", status=MeetingAttendeeStatus.ACCEPTED, is_organizer=False
    )
    await user.fetch_related("email_aliases")
    await another_user.fetch_related("email_aliases")
    users = [user, another_user]
    await meeting.add_attendee(attendee.as_meeting_attendee(users))
    await meeting.fetch_related("organization", "workspace__collaborators__user", "jobs__job", "recording")

    presenter = await MeetingPresenter.create(meeting, user, [user, another_user])

    assert presenter.current_user == user
    assert another_user in [attendee.user for attendee in presenter.attendees]
