import pytest

from app.models.collaboration.mailbox import MailboxEntry, mailbox_entry_registry
from app.models.collaboration.workspace import SubscriptionPreference, Visit
from app.models.workspaces.goals import Goal, GoalComment, GoalMailboxEntry, GoalUpdate
from config.enums import EventAction, GoalStatus, MailboxLabel, SubscriptionLevel
from tests.helpers.factories import (
    create_collaborator,
    create_goal,
    create_organization,
    create_user,
)


async def _active_goal_with_collaborator(organization, owner, collaborator):
    goal = await create_goal(
        organization_id=organization.id,
        creator_id=owner.id,
        owner_id=owner.id,
        title="Ship Q3",
        description="Improve onboarding conversion",
    )
    await goal.fetch_related("workspace")
    await create_collaborator(workspace_id=goal.workspace_id, user_id=collaborator.id)
    # ALL on both sides so an ordinary comment reaches everyone; who ends up unread is
    # then decided by the sender/content gate, not by subscription reach.
    await SubscriptionPreference.update_for(owner.id, {Goal.record_type: SubscriptionLevel.ALL})
    await SubscriptionPreference.update_for(collaborator.id, {Goal.record_type: SubscriptionLevel.ALL})
    return goal


async def _record_comment(goal, author, content, parent_id=None):
    comment = GoalComment(goal_id=goal.id, user_id=author.id, content=content, parent_id=parent_id)
    async with goal.workspace.record(EventAction.GOAL_COMMENTED, recordable=comment, creator_id=author.id) as rec:
        await comment.save(rec.using_db)
    return comment, rec.event


async def _record_update(goal, author, *, status, progress, answer):
    update = GoalUpdate(
        goal_id=goal.id,
        creator_id=author.id,
        status=status,
        progress=progress,
        question_text="How's it going?",
        answer_text=answer,
    )
    async with goal.workspace.record(EventAction.GOAL_UPDATE_POSTED, recordable=update, creator_id=author.id) as rec:
        await update.save(rec.using_db)
    return update, rec.event


async def _record_update_request(goal, requester, requestee, question):
    update = GoalUpdate(
        goal_id=goal.id,
        creator_id=requestee.id,
        requested_by_id=requester.id,
        status=goal.status,
        question_text=question,
    )
    async with goal.workspace.record(
        EventAction.GOAL_UPDATE_REQUESTED, recordable=update, creator_id=requester.id
    ) as rec:
        await update.save(rec.using_db)
    return update, rec.event


@pytest.mark.asyncio
async def test_registered_as_goal_mailbox_entry():
    assert mailbox_entry_registry[Goal.record_type] is GoalMailboxEntry


@pytest.mark.asyncio
async def test_comment_surfaces_unread_row_for_collaborators_not_author():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    goal = await _active_goal_with_collaborator(organization, owner, collaborator)
    _comment, event = await _record_comment(goal, owner, "Kicking this off")

    await GoalMailboxEntry(goal).sync(event=event, direct_recipients=[])

    collaborator_entry = await MailboxEntry.get(resource_gid=str(goal.global_id), owner_id=collaborator.id)
    assert MailboxLabel.INBOX in collaborator_entry.labels
    assert MailboxLabel.UNREAD in collaborator_entry.labels
    assert collaborator_entry.is_shared is True
    assert collaborator_entry.title == "Ship Q3"
    assert collaborator_entry.preview == "Improve onboarding conversion"
    # Latest event is the comment, so the second line is the comment body with its author.
    assert collaborator_entry.last_comment == "Kicking this off"
    assert collaborator_entry.last_comment_author_id == owner.id
    assert collaborator_entry.is_preview_comment is True

    # The author authored the event, so their row is never marked unread by their own comment.
    author_entry = await MailboxEntry.get_or_none(resource_gid=str(goal.global_id), owner_id=owner.id)
    assert author_entry is None or MailboxLabel.UNREAD not in author_entry.labels


@pytest.mark.asyncio
async def test_deleting_comment_clears_preview_and_does_not_resurface():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    goal = await _active_goal_with_collaborator(organization, owner, collaborator)
    comment, event = await _record_comment(goal, owner, "Original comment")
    await GoalMailboxEntry(goal).sync(event=event, direct_recipients=[])
    await GoalMailboxEntry(goal).mark_as_read(collaborator)

    await comment.soft_delete()
    # A comment delete records no workspace event, so a state-driven recompute must not
    # re-surface the row, and the deleted comment's text must not linger in the preview.
    await GoalMailboxEntry(goal).sync()

    entry = await MailboxEntry.get(resource_gid=str(goal.global_id), owner_id=collaborator.id)
    assert MailboxLabel.UNREAD not in entry.labels
    # The deleted comment's text is gone; with no visible comment the row falls back to a plain
    # activity line pinned to the comment event (the client renders it as "Goal updated").
    assert entry.last_comment is None
    assert entry.last_comment_author_id is None
    assert entry.last_event_id == event.id


@pytest.mark.asyncio
async def test_closed_comment_is_excluded_from_preview():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    goal = await _active_goal_with_collaborator(organization, owner, collaborator)
    first, _ = await _record_comment(goal, owner, "First thread")
    closed, event = await _record_comment(goal, owner, "Resolved thread")
    await closed.close()

    await GoalMailboxEntry(goal).sync(event=event, direct_recipients=[])

    entry = await MailboxEntry.get(resource_gid=str(goal.global_id), owner_id=collaborator.id)
    assert entry.last_comment == "First thread"
    assert entry.last_comment_author_id == first.user_id


@pytest.mark.asyncio
async def test_reply_preview_follows_its_root_visibility():
    # A reply is only visible on the goal panel when its root thread is. The newest comment in
    # each scenario is a reply hanging off a hidden root, so the preview must fall back to the
    # open "Live thread" root rather than surface a reply the panel won't render.
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    goal = await _active_goal_with_collaborator(organization, owner, collaborator)
    live, _ = await _record_comment(goal, owner, "Live thread")

    closed_root, _ = await _record_comment(goal, owner, "Resolved thread")
    await _record_comment(goal, owner, "Reply under resolved", parent_id=closed_root.id)
    await closed_root.close()

    deleted_root, _ = await _record_comment(goal, owner, "Doomed thread")
    _orphan, event = await _record_comment(goal, owner, "Reply orphaned by delete", parent_id=deleted_root.id)
    await deleted_root.soft_delete()

    await GoalMailboxEntry(goal).sync(event=event, direct_recipients=[])

    entry = await MailboxEntry.get(resource_gid=str(goal.global_id), owner_id=collaborator.id)
    assert entry.last_comment == "Live thread"
    assert entry.last_comment_author_id == live.user_id


@pytest.mark.asyncio
async def test_mark_as_read_survives_sync_for_the_same_comment():
    # Regression (#8816): if mark_as_read doesn't advance last_activity_at, a
    # SyncMailboxJob for the same comment that lands afterward sees a stale cursor and
    # re-surfaces UNREAD. Run the calls in the race-distinguishing order: mark_as_read,
    # then the comment's sync.
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    goal = await _active_goal_with_collaborator(organization, owner, collaborator)
    await GoalMailboxEntry(goal).sync()
    await GoalMailboxEntry(goal).mark_as_read(collaborator)

    _comment, event = await _record_comment(goal, owner, "Live update")

    await GoalMailboxEntry(goal).mark_as_read(collaborator)
    await GoalMailboxEntry(goal).sync(event=event, direct_recipients=[])

    entry = await MailboxEntry.get(resource_gid=str(goal.global_id), owner_id=collaborator.id)
    assert entry.read_at is not None
    assert MailboxLabel.UNREAD not in entry.labels, "SyncMailboxJob clobbered the client mark_read (#8816)"


@pytest.mark.asyncio
async def test_latest_event_drives_the_second_line():
    # The second line always summarizes the goal's latest event — why it surfaced. Walk the row
    # through a posted update, an update request, and a state change; each supersedes the last.
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    goal = await _active_goal_with_collaborator(organization, owner, collaborator)
    _comment, comment_event = await _record_comment(goal, owner, "Kicking this off")
    await GoalMailboxEntry(goal).sync(event=comment_event, direct_recipients=[])

    # Posted update -> its body, attributed to the poster (status/progress ride the header).
    _update, update_event = await _record_update(
        goal, owner, status=GoalStatus.AT_RISK, progress=0.4, answer="Slipped a week"
    )
    await GoalMailboxEntry(goal).sync(event=update_event, direct_recipients=[])
    entry = await MailboxEntry.get(resource_gid=str(goal.global_id), owner_id=collaborator.id)
    assert entry.last_comment == "Slipped a week"
    assert entry.last_comment_author_id == owner.id
    # An update is authored but not a comment, so the client renders it without the chip.
    assert entry.is_preview_comment is False
    # Authored previews carry their own text — no activity event is pinned.
    assert entry.last_event_id is None
    # The description still rides the preview slot for the title tooltip.
    assert entry.preview == "Improve onboarding conversion"

    # Requested update -> a plain activity line; the model pins the event and the client phrases
    # "Update requested from <requester> - <question>" from it, so no display string is stored.
    _requested, request_event = await _record_update_request(goal, owner, collaborator, "Where are we?")
    await GoalMailboxEntry(goal).sync(event=request_event, direct_recipients=[])
    entry = await MailboxEntry.get(resource_gid=str(goal.global_id), owner_id=collaborator.id)
    assert entry.last_comment is None
    assert entry.last_comment_author_id is None
    assert entry.last_event_id == request_event.id

    # State change -> a plain activity line pinned to the event; the client phrases the summary.
    async with goal.workspace.record(EventAction.GOAL_UPDATED, creator_id=owner.id) as rec:
        rec.event.details["status"] = [GoalStatus.ON_TRACK.value, GoalStatus.OFF_TRACK.value]
    await GoalMailboxEntry(goal).sync(event=rec.event, direct_recipients=[])
    entry = await MailboxEntry.get(resource_gid=str(goal.global_id), owner_id=collaborator.id)
    assert entry.last_comment is None
    assert entry.last_comment_author_id is None
    assert entry.last_event_id == rec.event.id


@pytest.mark.asyncio
async def test_sync_soft_deletes_on_goal_deletion():
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    goal = await _active_goal_with_collaborator(organization, owner, collaborator)
    _comment, event = await _record_comment(goal, owner, "A comment")
    await GoalMailboxEntry(goal).sync(event=event, direct_recipients=[])

    assert await MailboxEntry.get_or_none(resource_gid=str(goal.global_id), owner_id=collaborator.id) is not None

    await goal.soft_delete()
    await GoalMailboxEntry(goal).sync()

    assert await MailboxEntry.filter(resource_gid=str(goal.global_id)).count() == 0
    deleted_entries = await MailboxEntry.unscoped.filter(resource_gid=str(goal.global_id))
    assert deleted_entries
    assert all(e.is_deleted for e in deleted_entries)


@pytest.mark.asyncio
async def test_mark_read_and_unread_do_not_touch_visit_cursor():
    # The goal "new activity" divider is a visit-on-open cursor, so inbox triage must not move it.
    # This is the deliberate split from chat, whose mark_as_read/unread DO bridge into Visit.
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    collaborator = await create_user(organization_id=organization.id)

    goal = await _active_goal_with_collaborator(organization, owner, collaborator)
    _comment, event = await _record_comment(goal, owner, "Kicking this off")
    await GoalMailboxEntry(goal).sync(event=event, direct_recipients=[])

    await GoalMailboxEntry(goal).mark_as_read(collaborator)
    assert await Visit.filter(user_id=collaborator.id, workspace_id=goal.workspace_id).count() == 0

    await GoalMailboxEntry(goal).mark_as_unread(collaborator)
    assert await Visit.filter(user_id=collaborator.id, workspace_id=goal.workspace_id).count() == 0
