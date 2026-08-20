import pytest

from app.models.collaboration.workspace import Visit
from app.models.workspaces.email.thread import EmailThreadComment
from app.models.workspaces.goals import GoalComment
from app.presenters.activity import EventPresenter
from app.presenters.goals import GoalTimelinePresenter
from config.enums import EventAction, GoalStatus
from tests.helpers.factories import (
    create_chat,
    create_document,
    create_email_thread,
    create_goal,
)


@pytest.mark.asyncio
async def test_timeline_presenter():
    thread = await create_email_thread()
    await thread.fetch_related("workspace")
    user_id = thread.creator_id

    comment_one = EmailThreadComment(email_thread_id=thread.id, user_id=user_id)
    async with thread.workspace.record(EventAction.COMMENTED, recordable=comment_one, creator_id=user_id) as recording:
        await comment_one.save(recording.using_db)

    await Visit.record(workspace_id=thread.workspace_id, user_id=user_id)

    comment_two = EmailThreadComment(email_thread_id=thread.id, user_id=user_id)
    async with thread.workspace.record(EventAction.COMMENTED, recordable=comment_two, creator_id=user_id) as recording:
        await comment_two.save(recording.using_db)

    await thread.workspace.fetch_related("events")
    activity = await EventPresenter.create_from_list(thread.workspace.events)
    assert len(activity) == 2
    assert activity[1].model.action == EventAction.COMMENTED
    assert activity[0].model.action == EventAction.COMMENTED


@pytest.mark.asyncio
async def test_decided_events_present_on_document_and_chat_workspaces():
    # DECIDED records the workspace resource as the recordable; Document and
    # Chat must resolve in RecordableTypeMap or these events silently drop.
    document = await create_document()
    await document.fetch_related("workspace")
    async with document.workspace.record(EventAction.DECIDED, recordable=document, creator_id=document.creator_id):
        pass

    chat = await create_chat()
    await chat.fetch_related("workspace")
    async with chat.workspace.record(EventAction.DECIDED, recordable=chat, creator_id=chat.creator_id):
        pass

    for workspace in (document.workspace, chat.workspace):
        await workspace.fetch_related("events")
        activity = await EventPresenter.create_from_list(workspace.events)
        assert [p.model.action for p in activity] == [EventAction.DECIDED]


@pytest.mark.asyncio
async def test_goal_timeline_presenter_nests_reply_comments():
    goal = await create_goal()

    parent_comment = GoalComment(content="parent", goal_id=goal.id, user_id=goal.creator_id)
    async with goal.workspace.record(
        EventAction.GOAL_COMMENTED, recordable=parent_comment, creator_id=goal.creator_id
    ) as recording:
        await parent_comment.save(recording.using_db)

    reply_one = GoalComment(content="reply 1", goal_id=goal.id, user_id=goal.creator_id, parent_id=parent_comment.id)
    async with goal.workspace.record(
        EventAction.GOAL_COMMENTED, recordable=reply_one, creator_id=goal.creator_id
    ) as recording:
        await reply_one.save(recording.using_db)

    reply_two = GoalComment(content="reply 2", goal_id=goal.id, user_id=goal.creator_id, parent_id=parent_comment.id)
    async with goal.workspace.record(
        EventAction.GOAL_COMMENTED, recordable=reply_two, creator_id=goal.creator_id
    ) as recording:
        await reply_two.save(recording.using_db)

    await goal.workspace.fetch_related("events")
    events = await EventPresenter.create_from_list(goal.workspace.events)
    timeline = GoalTimelinePresenter(events=events, goal_status=GoalStatus.ON_TRACK)

    comment_events = [e for e in timeline.events if e.action == EventAction.GOAL_COMMENTED]
    assert len(comment_events) == 1
    assert comment_events[0].recordable.id == parent_comment.id
    assert len(comment_events[0].replies) == 2
    assert comment_events[0].replies[0].recordable.id == reply_one.id
    assert comment_events[0].replies[1].recordable.id == reply_two.id


@pytest.mark.asyncio
async def test_goal_timeline_presenter_orphan_replies_stay_standalone():
    goal = await create_goal()

    parent_comment = GoalComment(content="parent", goal_id=goal.id, user_id=goal.creator_id)
    async with goal.workspace.record(
        EventAction.GOAL_COMMENTED, recordable=parent_comment, creator_id=goal.creator_id
    ) as recording:
        await parent_comment.save(recording.using_db)

    reply = GoalComment(content="reply", goal_id=goal.id, user_id=goal.creator_id, parent_id=parent_comment.id)
    async with goal.workspace.record(
        EventAction.GOAL_COMMENTED, recordable=reply, creator_id=goal.creator_id
    ) as recording:
        await reply.save(recording.using_db)

    await goal.workspace.fetch_related("events")
    all_events = await EventPresenter.create_from_list(goal.workspace.events)
    all_events.reverse()

    events_without_parent = [e for e in all_events if e.recordable.id != parent_comment.id]
    timeline = GoalTimelinePresenter(events=events_without_parent, goal_status=GoalStatus.ON_TRACK)

    comment_events = [e for e in timeline.events if e.action == EventAction.GOAL_COMMENTED]
    assert len(comment_events) == 1
    assert comment_events[0].recordable.id == reply.id
    assert len(comment_events[0].replies) == 0
