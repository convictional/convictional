import pytest
from pycrdt import Doc, Text

from app.models.collaboration.live import LiveDocumentUpdate
from app.models.workspaces.meetings import Meeting
from app.presenters.meeting import MeetingSummaryPresenter
from infra.messaging import Topic
from tests.helpers.factories import create_meeting, create_user


@pytest.mark.asyncio
async def test_fetch_agenda_map_detects_db_and_livedocument_agendas():
    """fetch_agenda_map flags meetings with a text agenda or a live-document agenda, and only those."""
    user = await create_user()

    db_agenda = await Meeting.create(
        title="DB agenda",
        agenda="# Topics\n\n- Item 1\n- Item 2",
        organization_id=user.organization_id,
        creator_id=user.id,
    )
    empty_agenda = await Meeting.create(
        title="Whitespace agenda",
        agenda="   \n\n   ",
        organization_id=user.organization_id,
        creator_id=user.id,
    )
    live_agenda = await create_meeting(organization_id=user.organization_id)
    no_agenda = await create_meeting(organization_id=user.organization_id)

    topic = Topic("meeting_agenda", meeting_id=str(live_agenda.id))
    doc: Doc = Doc()
    text = doc.get("markdown", type=Text)
    text += "# Meeting Agenda\n\n- Item 1: Discuss project timeline\n- Item 2: Review budget"
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=doc.get_update())

    agenda_map = await MeetingSummaryPresenter.fetch_agenda_map([db_agenda, empty_agenda, live_agenda, no_agenda])

    assert agenda_map[db_agenda.id] is True
    assert agenda_map[live_agenda.id] is True
    assert agenda_map[empty_agenda.id] is False
    assert agenda_map[no_agenda.id] is False


@pytest.mark.asyncio
async def test_meeting_model_has_agenda():
    """Test that Meeting.has_agenda() checks both database field and LiveDocument."""
    user = await create_user()

    # Test 1: Meeting with no agenda at all
    meeting_no_agenda = await create_meeting(organization_id=user.organization_id)
    assert await meeting_no_agenda.has_agenda() is False, "Meeting with no agenda should return False"

    # Test 2: Meeting with agenda in database field
    meeting_db_agenda = await Meeting.create(
        title="Meeting with DB Agenda",
        agenda="# Important Topics\n\n- Topic 1\n- Topic 2",
        organization_id=user.organization_id,
        creator_id=user.id,
    )
    assert await meeting_db_agenda.has_agenda() is True, "Meeting with database agenda should return True"

    # Test 3: Meeting with empty agenda in database field (whitespace only)
    meeting_empty_agenda = await Meeting.create(
        title="Meeting with Empty Agenda",
        agenda="   \n\n   ",
        organization_id=user.organization_id,
        creator_id=user.id,
    )
    assert await meeting_empty_agenda.has_agenda() is False, "Meeting with empty/whitespace agenda should return False"

    # Test 4: Meeting with LiveDocument agenda
    meeting_live_agenda = await create_meeting(organization_id=user.organization_id)
    topic = Topic("meeting_agenda", meeting_id=str(meeting_live_agenda.id))
    doc: Doc = Doc()
    text = doc.get("markdown", type=Text)
    text += "# Live Document Agenda\n\n- Collaborative point 1\n- Collaborative point 2"
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=doc.get_update())
    assert await meeting_live_agenda.has_agenda() is True, "Meeting with LiveDocument agenda should return True"

    # Test 5: Meeting with both database and LiveDocument agenda
    meeting_both = await Meeting.create(
        title="Meeting with Both Agendas",
        agenda="Database agenda",
        organization_id=user.organization_id,
        creator_id=user.id,
    )
    topic_both = Topic("meeting_agenda", meeting_id=str(meeting_both.id))
    doc_both: Doc = Doc()
    text_both = doc_both.get("markdown", type=Text)
    text_both += "LiveDocument agenda"
    await LiveDocumentUpdate.create(topic_name=topic_both.name, update_data=doc_both.get_update())
    assert await meeting_both.has_agenda() is True, "Meeting with both agendas should return True"
