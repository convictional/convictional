from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time
from tortoise.exceptions import DoesNotExist

from app.models.accounts import Organization
from app.models.collaboration.workspace import (
    Event,
    MentionResolver,
    Workspace,
    WorkspaceMixin,
    WorkspaceResourceFetcher,
)
from app.models.workspaces.goals import Goal
from config.enums import EventAction, Sharing
from tests.helpers.factories import (
    create_collaborator,
    create_goal,
    create_meeting,
    create_user,
)


@pytest.mark.asyncio
async def test_indexing_activity_at_folds_in_workspace_events():
    # The WorkspaceMixin base recency signal is max(updated_at, workspace.last_event_at): with no
    # activity it falls back to the resource's own updated_at; a later event carries it forward
    # even though recording an event never re-saves the resource. Requires events prefetched.
    organization = await Organization.create(domain="example.com")
    user = await create_user(organization_id=organization.id)

    one_month_ago = datetime.now(UTC) - timedelta(days=30)
    with freeze_time(one_month_ago):
        goal = await create_goal(organization_id=organization.id, creator_id=user.id)

    await goal.fetch_related("workspace__events")
    assert goal.indexing_activity_at == goal.updated_at

    async with goal.workspace.record(EventAction.GOAL_COMMENTED, creator_id=user.id) as recording:
        pass
    await goal.fetch_related("workspace__events")

    assert recording.event.created_at > goal.updated_at
    assert goal.indexing_activity_at == recording.event.created_at


@pytest.mark.asyncio
async def test_recording_events():
    organization = await Organization.create(domain="example.com")
    user = await create_user(email="foo@example.com", organization_id=organization.id)
    goal = Goal(title="Test Goal", description="desc", organization_id=organization.id, creator_id=user.id)

    async with goal.workspace.record(EventAction.GOAL_CREATED, creator_id=user.id) as recording:
        recording.event.details["foo"] = "bar"
        await goal.save(recording.using_db)

    events = await Event.all()
    assert len(events) == 1
    assert events[0].action == EventAction.GOAL_CREATED
    assert events[0].creator_id == user.id
    assert events[0].recordable_id == goal.id
    assert events[0].recordable_type == "Goal"
    assert events[0].details["foo"] == "bar"
    assert events[0].details["title"] == [None, "Test Goal"]


@pytest.mark.asyncio
async def test_workspace_resource_fetcher():
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id)
    meeting = await create_meeting(organization_id=user.organization_id)
    deleted_goal = await create_goal(organization_id=user.organization_id, deleted_at=datetime.now(UTC))

    await goal.fetch_related("workspace")
    await meeting.fetch_related("workspace")
    workspaces = [goal.workspace, meeting.workspace, deleted_goal.workspace]

    # Test loading without prefetching
    await WorkspaceResourceFetcher(workspaces).fetch()
    assert workspaces[0].resource == goal
    assert workspaces[1].resource == meeting

    # Test loading with prefetching
    await WorkspaceResourceFetcher(workspaces, prefetch_map={Goal: ["comments"]}).fetch()
    assert workspaces[0].resource == goal
    assert workspaces[1].resource == meeting
    assert isinstance(workspaces[0].resource, Goal)


@pytest.mark.asyncio
async def test_fetching_workspace_relations():
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id)

    await goal.fetch_related("workspace")
    assert goal.workspace.resource is goal

    goal = await Goal.get(id=goal.id).prefetch_related("workspace")
    assert goal.workspace.resource is goal


@pytest.mark.asyncio
async def test_fetching_workspace_resources():
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id)
    workspaces = await Workspace.all()
    assert len(workspaces) == 1
    workspace = workspaces[0]

    result: WorkspaceMixin | None = await workspace.fetch_resource()
    assert result == goal
    assert workspace.resource == goal

    result = await workspace.fetch_resource_or_none()
    assert result == goal
    assert workspace.resource == goal

    await goal.soft_delete()

    with pytest.raises(DoesNotExist):
        await workspace.fetch_resource()

    result = await workspace.fetch_resource_or_none()
    assert result is None


@pytest.mark.asyncio
async def test_syncing_workspace_sharing():
    goal = await create_goal(sharing=Sharing.PRIVATE)
    assert goal.workspace.sharing == Sharing.PRIVATE
    await goal.fetch_related("workspace")
    assert goal.workspace.sharing == Sharing.PRIVATE

    goal.sharing = Sharing.ORGANIZATION
    await goal.save()
    await goal.fetch_related("workspace")
    assert goal.workspace.sharing == Sharing.ORGANIZATION


@pytest.mark.asyncio
async def test_mention_resolving():
    alice = await create_user(name="Alice Clams")
    bob = await create_user(name="Bob Clams", organization_id=alice.organization_id)
    charlie = await create_user(name="Charlie Clams", organization_id=alice.organization_id)
    goal = await create_goal(creator_id=alice.id, organization_id=alice.organization_id, sharing=Sharing.PRIVATE)

    # Test resolving mentions ignores people without access
    resolver = MentionResolver(
        recordable=goal,
        workspace=goal.workspace,
        content="Hey @[Bob Clams], how are you doing?",
        creator_id=alice.id,
    )
    assert resolver.possible_mentions == ["Bob Clams"]
    assert (await resolver.possible_users()) == [alice]
    await resolver.resolve()
    assert len(resolver.mentions) == 0

    # Test resolving mentions for collaborators
    await create_collaborator(workspace_id=goal.workspace_id, user_id=bob.id)
    await goal.fetch_related("workspace__collaborators__user")
    resolver = MentionResolver(
        recordable=goal,
        workspace=goal.workspace,
        content="Hey @[Bob Clams], how are you doing?",
        creator_id=alice.id,
    )
    assert resolver.possible_mentions == ["Bob Clams"]
    assert (await resolver.possible_users()) == [alice, bob]
    await resolver.resolve()

    assert len(resolver.mentions) == 1
    assert resolver.mentions[0].is_new
    assert len(resolver.mentions[0].content) > 0
    assert resolver.mentions[0].mentioned_id == bob.id
    assert resolver.mentions[0].creator_id == alice.id
    assert resolver.mentions[0].workspace_id == goal.workspace_id
    assert resolver.mentions[0].recordable_gid == goal.global_id

    # Test resolving mentions for the organization
    await goal.update_from_dict({"sharing": Sharing.ORGANIZATION}).save()
    resolver = MentionResolver(
        recordable=goal,
        workspace=goal.workspace,
        content="Hey @[Charlie Clams], how are you doing?",
        creator_id=alice.id,
    )
    assert resolver.possible_mentions == ["Charlie Clams"]
    assert (await resolver.possible_users()) == [alice, bob, charlie]
    await resolver.resolve()

    assert len(resolver.mentions) == 1
    assert resolver.mentions[0].is_new
    assert len(resolver.mentions[0].content) > 0
    assert resolver.mentions[0].mentioned_id == charlie.id
    assert resolver.mentions[0].creator_id == alice.id
    assert resolver.mentions[0].workspace_id == goal.workspace_id
    assert resolver.mentions[0].recordable_gid == goal.global_id

    # Test mentions are not duplicated, save the previous mentions to test for duplicates
    for mention in resolver.mentions:
        await mention.save()
    resolver = MentionResolver(
        recordable=goal,
        workspace=goal.workspace,
        content="Hey @[Charlie Clams], how are you doing?",
        creator_id=alice.id,
    )
    await resolver.resolve()

    assert len(resolver.mentions) == 1
    assert not resolver.mentions[0].is_new
    assert len(resolver.mentions[0].content) > 0
    assert resolver.mentions[0].mentioned_id == charlie.id
    assert resolver.mentions[0].creator_id == alice.id
    assert resolver.mentions[0].workspace_id == goal.workspace_id
    assert resolver.mentions[0].recordable_gid == goal.global_id
