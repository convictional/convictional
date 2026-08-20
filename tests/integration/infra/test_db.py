from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pypika_tortoise import Order  # type: ignore
from tortoise import BaseDBAsyncClient
from tortoise.exceptions import DoesNotExist
from tortoise.functions import Max

from app.models.accounts import Organization, User
from app.models.workspaces.goals import Goal
from app.models.workspaces.posts import Post, PostComment
from config.enums import EventAction, RecordModelEvent
from infra.db import (
    Change,
    GlobalID,
    Pagination,
    RecordModel,
    after_commit,
    allow_soft_deleted,
    observe,
    transaction,
    unobserve,
)
from tests.helpers.factories import (
    create_goal,
    create_organization,
    create_post,
    create_user,
)


@pytest.mark.asyncio
async def test_change_tracking():
    organization = Organization(name="Test Organization")
    assert organization.is_new

    organization = await create_organization(name="Test Organization")
    assert organization.name == "Test Organization"
    assert organization.changes == {}
    assert not organization.is_changed
    assert not organization.is_new

    organization.name = "New Name"
    assert organization.name == "New Name"
    assert organization.changes == {"name": ("Test Organization", "New Name")}
    assert organization.is_changed
    assert not organization.is_new

    await organization.save()
    assert organization.changes == {}
    assert not organization.is_changed

    organization.name = "Another Name"
    await organization.refresh_from_db()
    assert organization.changes == {}
    assert not organization.is_changed

    organization = await create_organization(name="Test Organization")
    user = await create_user(organization=organization, organization_id=organization.id)
    user = await User.get(id=user.id)
    user.organization = organization
    assert not user.changes


@pytest.mark.asyncio
async def test_soft_deleting():
    organization = await create_organization()
    assert not organization.is_deleted
    assert await Organization.all().count() == 1
    assert await Organization.deleted.count() == 0
    assert await Organization.unscoped.count() == 1

    await organization.soft_delete()
    assert organization.is_deleted
    assert await Organization.all().count() == 0
    assert await Organization.deleted.count() == 1
    assert await Organization.unscoped.count() == 1

    with pytest.raises(DoesNotExist):
        await Organization.get(id=organization.id)

    async with allow_soft_deleted():
        assert await Organization.get(id=organization.id) == organization

    await organization.restore()
    assert not organization.is_deleted
    assert await Organization.all().count() == 1
    assert await Organization.deleted.count() == 0
    assert await Organization.unscoped.count() == 1

    assert await Organization.get(id=organization.id) == organization


@pytest.mark.asyncio
async def test_global_id_from_record():
    user = await create_user()
    goal = await create_post(organization_id=user.organization_id)

    gid = GlobalID.from_record(goal)
    assert gid.is_internal
    assert gid.record_type == "Post"
    assert gid.record_id == goal.id
    assert str(gid) == f"gid://convictional/Post/{goal.id}"
    assert GlobalID.parse(str(gid)) == gid


@pytest.mark.asyncio
async def test_global_id_parse():
    goal = await create_post()
    gid_str = f"gid://convictional/Post/{goal.id}"
    gid = GlobalID.parse(gid_str)
    assert isinstance(gid, GlobalID)
    assert gid.app_name == "convictional"
    assert gid.record_type == "Post"
    assert gid.record_id == goal.id
    assert gid.is_internal

    url_str = "https://www.example.com"
    gid = GlobalID.parse(url_str)
    assert str(gid) == url_str
    assert gid.app_name is None
    assert gid.record_type is None
    assert gid.record_id is None
    assert not gid.is_internal


@pytest.mark.asyncio
async def test_pagination():
    post_1 = await create_post(title="E")
    post_2 = await create_post(title="D")
    post_3 = await create_post(title="C")
    post_4 = await create_post(title="B")
    post_5 = await create_post(title="A")

    #
    # Test basic pagination
    #
    #
    pagination = await Pagination.create(Post, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [("created_at", Order.desc), ("id", Order.asc)]
    assert len(pagination) == 2
    assert pagination[0] == post_5
    assert pagination[1] == post_4

    pagination = await Pagination.create(Post, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert len(pagination) == 2
    assert pagination[0] == post_3
    assert pagination[1] == post_2

    pagination = await Pagination.create(Post, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 1
    assert pagination[0] == post_1

    #
    # Test pagination with custom sorting
    #
    #
    queryset = Post.all().order_by("title")
    pagination = await Pagination.create(Post, queryset=queryset, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [("title", Order.asc), ("id", Order.asc)]
    assert len(pagination) == 2
    assert pagination[0] == post_5
    assert pagination[1] == post_4

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert len(pagination) == 2
    assert pagination[0] == post_3
    assert pagination[1] == post_2

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 1
    assert pagination[0] == post_1

    queryset = Post.all().order_by("-title")
    pagination = await Pagination.create(Post, queryset=queryset, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [("title", Order.desc), ("id", Order.asc)]
    assert len(pagination) == 2
    assert pagination[0] == post_1
    assert pagination[1] == post_2

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert len(pagination) == 2
    assert pagination[0] == post_3
    assert pagination[1] == post_4

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 1
    assert pagination[0] == post_5

    #
    # Test pagination with filtering
    #
    #
    queryset = Post.all().filter(title__gte="B")
    pagination = await Pagination.create(Post, queryset=queryset, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [("created_at", Order.desc), ("id", Order.asc)]
    assert len(pagination) == 2
    assert pagination[0] == post_4
    assert pagination[1] == post_3

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 2
    assert pagination[0] == post_2
    assert pagination[1] == post_1


@pytest.mark.asyncio
async def test_pagination_tie_breakers():
    # Create a testset with many duplicate sorted values
    now = datetime.now()
    await create_post(title="E", created_at=now)
    await create_post(title="D", created_at=now)
    await create_post(title="C", created_at=now)
    await create_post(title="B", created_at=now)
    await create_post(title="A", created_at=now)

    # Refetch the models, as IDs are not ordered
    models = await Post.all().order_by("id")

    # Test pagination with tie-breakers
    pagination = await Pagination.create(Post, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [("created_at", Order.desc), ("id", Order.asc)]
    assert len(pagination) == 2
    assert pagination[0] == models[0]
    assert pagination[1] == models[1]

    pagination = await Pagination.create(Post, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert len(pagination) == 2
    assert pagination[0] == models[2]
    assert pagination[1] == models[3]

    pagination = await Pagination.create(Post, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 1
    assert pagination[0] == models[4]

    #
    # Test pagination with custom sorting
    #
    #

    queryset = Post.all().order_by("title")
    models = await queryset  # Fetch models in the order that pagination will return them
    pagination = await Pagination.create(Post, queryset=queryset, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [("title", Order.asc), ("id", Order.asc)]
    assert len(pagination) == 2
    assert pagination[0] == models[0]
    assert pagination[1] == models[1]

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert len(pagination) == 2
    assert pagination[0] == models[2]
    assert pagination[1] == models[3]

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 1
    assert pagination[0] == models[4]

    queryset = Post.all().order_by("-title")
    pagination = await Pagination.create(Post, queryset=queryset, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [("title", Order.desc), ("id", Order.asc)]
    assert len(pagination) == 2
    assert pagination[0] == models[4]
    assert pagination[1] == models[3]

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert len(pagination) == 2
    assert pagination[0] == models[2]
    assert pagination[1] == models[1]

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 1
    assert pagination[0] == models[0]

    #
    # Test pagination with filtering
    #
    #
    queryset = Post.all().filter(title__gte="B")
    models = await queryset.order_by("id")  # We know models will be sorted by the tiebreaker

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [("created_at", Order.desc), ("id", Order.asc)]
    assert len(pagination) == 2
    assert pagination[0] == models[0]
    assert pagination[1] == models[1]

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 2
    assert pagination[0] == models[2]
    assert pagination[1] == models[3]


@pytest.mark.asyncio
async def test_pagination_with_nulls():
    now = datetime.now().date()
    goal = await create_goal(title="A", target_date=now + timedelta(days=1))
    org_id = goal.organization_id
    creator_id = goal.creator_id
    goal_2 = await create_goal(title="B", target_date=None, organization_id=org_id, creator_id=creator_id)
    goal_3 = await create_goal(
        title="C", target_date=now + timedelta(days=2), organization_id=org_id, creator_id=creator_id
    )
    goal_4 = await create_goal(title="D", target_date=None, organization_id=org_id, creator_id=creator_id)
    goal_5 = await create_goal(
        title="E", target_date=now + timedelta(days=3), organization_id=org_id, creator_id=creator_id
    )

    queryset = Goal.all().order_by("target_date", "title")
    pagination = await Pagination[Goal].create(Goal, queryset=queryset, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [
        ("target_date", Order.asc),
        ("title", Order.asc),
        ("id", Order.asc),
    ]
    assert len(pagination) == 2
    assert pagination[0] == goal
    assert pagination.results[0].target_date == now + timedelta(days=1)
    assert pagination[1] == goal_3
    assert pagination.results[1].target_date == now + timedelta(days=2)

    pagination = await Pagination.create(Goal, queryset=queryset, per_page=2, cursor=pagination.next_cursor)

    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert len(pagination) == 2
    assert pagination[0] == goal_5
    assert pagination.results[0].target_date == now + timedelta(days=3)
    assert pagination[1] == goal_2
    # Pagination uses coalesce to ensure nulls are final
    # Check that target_date is not overwritten by the coalesced value
    assert pagination.results[1].target_date is None

    pagination = await Pagination.create(Goal, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 1
    assert pagination[0] == goal_4
    assert pagination.results[0].target_date is None


@pytest.mark.asyncio
async def test_pagination_with_annotate():
    first = await create_post()
    second = await create_post()
    third = await create_post()

    queryset = Post.all().annotate(last_commented_at=Max("comments__created_at")).order_by("-last_commented_at")

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2)
    assert pagination.per_page == 2
    assert pagination.cursor is None
    assert pagination.has_next
    assert pagination.next_cursor is not None
    assert pagination.sort_fields == [("last_commented_at", Order.desc), ("id", Order.asc)]
    assert len(pagination) == 2
    assert pagination[0] == third
    assert pagination[1] == second

    pagination = await Pagination.create(Post, queryset=queryset, per_page=2, cursor=pagination.next_cursor)
    assert pagination.per_page == 2
    assert pagination.cursor is not None
    assert not pagination.has_next
    assert pagination.next_cursor is None
    assert len(pagination) == 1
    assert pagination[0] == first


@pytest.mark.asyncio
async def test_get_or_init():
    post = await create_post()
    existing = await Post.get_or_init(id=post.id)
    assert not existing.is_new
    assert existing == post

    new = await Post.get_or_init(title="Test Post")
    assert new.is_new
    assert new != post
    assert new.title == "Test Post"


@pytest.mark.asyncio
async def test_copying():
    original = await create_organization(name="Foo")
    copied = await original.copy({"domain": "copied.com"})
    assert copied.name == "Foo"
    assert copied.domain == "copied.com"
    assert copied.domain == "copied.com"
    assert copied.created_at != original.created_at
    assert copied.updated_at != original.updated_at


@pytest.mark.asyncio
async def test_transactions():
    creator = await create_user()
    post = Post(title="foo", creator_id=creator.id, organization_id=creator.organization_id)

    async with post.workspace.record(EventAction.POST_CREATED, creator_id=creator.id) as recording:
        await post.save(using_db=recording.using_db)
        comment = PostComment(post_id=post.id, user_id=creator.id, content="bar")
        async with post.workspace.record(
            EventAction.POST_COMMENTED, recordable=comment, creator_id=creator.id
        ) as comment_recording:
            await comment.save(using_db=comment_recording.using_db)

    post = await Post.get(id=post.id)
    assert post
    comment = await PostComment.get(id=comment.id)
    assert comment


@pytest.fixture
def observing():
    observations = []

    async def example_observer(
        instance: RecordModel, changes: dict[str, Change], using_db: BaseDBAsyncClient | None = None
    ):
        observations.append((instance.global_id, changes))

    observe(RecordModelEvent.CREATE, Organization, example_observer)
    observe(RecordModelEvent.UPDATE, Organization, example_observer)
    observe(RecordModelEvent.DELETE, Organization, example_observer)

    yield observations

    unobserve(RecordModelEvent.CREATE, Organization, example_observer)
    unobserve(RecordModelEvent.UPDATE, Organization, example_observer)
    unobserve(RecordModelEvent.DELETE, Organization, example_observer)


@pytest.mark.asyncio
async def test_observers(observing):
    organization = await create_organization(name="Foo")
    assert len(observing) == 1
    assert observing[0][0] == organization.global_id
    assert len(observing[0][1]) == 0

    organization.name = "Bar"
    await organization.save()

    assert len(observing) == 2
    assert observing[1][0] == organization.global_id
    assert len(observing[1][1]) == 1
    assert observing[1][1]["name"] == ("Foo", "Bar")

    await organization.delete()
    assert len(observing) == 3
    assert observing[2][0] == organization.global_id
    assert len(observing[2][1]) == 0


@pytest.mark.asyncio
async def test_after_commit():
    executed_callbacks = []

    async def callback1(using_db: BaseDBAsyncClient):
        executed_callbacks.append("callback1")

    async def callback2(using_db: BaseDBAsyncClient):
        executed_callbacks.append("callback2")

    # Test 1: Successful transaction - callbacks should execute
    async with transaction():
        await after_commit(callback1)
        await after_commit(callback2)
        await create_user()

    assert executed_callbacks == ["callback1", "callback2"]

    # Test 2: Failed transaction - callbacks should NOT execute
    executed_callbacks.clear()

    try:
        async with transaction():
            await after_commit(callback1)
            await create_user()
            raise Exception("Simulated failure")
    except Exception:
        pass

    assert executed_callbacks == []

    # Test 3: Nested transactions - callbacks execute at outermost level
    executed_callbacks.clear()

    async with transaction() as outer_conn:
        await after_commit(callback1)
        user = await create_user(using_db=outer_conn)

        async with transaction(using_db=outer_conn):
            await after_commit(callback2)
            await user.save(using_db=outer_conn)

        # Nested transaction completed, but callbacks not yet executed
        assert executed_callbacks == []

    # Now both callbacks should have executed
    assert executed_callbacks == ["callback1", "callback2"]

    # Test 4: Exception in callback doesn't prevent other callbacks
    executed_callbacks.clear()

    async def failing_callback(using_db: BaseDBAsyncClient):
        executed_callbacks.append("failing_callback")
        raise Exception("Callback failed")

    async def normal_callback(using_db: BaseDBAsyncClient):
        executed_callbacks.append("normal_callback")

    # Transaction should succeed even if callback fails
    async with transaction():
        await after_commit(failing_callback)
        await after_commit(normal_callback)
        await create_user()

    # Both callbacks should have been attempted
    assert executed_callbacks == ["failing_callback", "normal_callback"]

    # Test 5: Outside transaction - callbacks execute immediately
    executed_callbacks.clear()

    await after_commit(callback1)
    # Callback should have executed immediately since we're not in a transaction
    assert executed_callbacks == ["callback1"]

    # Multiple callbacks outside transaction also execute immediately
    await after_commit(callback2)
    assert executed_callbacks == ["callback1", "callback2"]


@pytest.mark.asyncio
async def test_timestamp_automatic_behavior():
    organization = await create_organization(name="Test Org")

    assert organization.created_at is not None
    assert organization.updated_at is not None
    assert organization.created_at == organization.updated_at

    original_created_at = organization.created_at
    original_updated_at = organization.updated_at
    organization.name = "Updated Org"
    await organization.save()

    assert organization.created_at == original_created_at
    assert organization.updated_at > original_updated_at


@pytest.mark.asyncio
async def test_timestamp_manual_override():
    custom_created_at = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)
    organization = Organization(name="Test Org", created_at=custom_created_at)
    await organization.save()
    assert organization.created_at == custom_created_at

    await organization.refresh_from_db()
    assert organization.created_at == custom_created_at
    assert organization.updated_at is not None

    custom_updated_at = datetime(2021, 6, 15, 14, 30, 0, tzinfo=UTC)
    organization.name = "Updated Org"
    organization.updated_at = custom_updated_at
    await organization.save()

    await organization.refresh_from_db()
    assert organization.created_at == custom_created_at
    assert organization.updated_at == custom_updated_at

    custom_both_created = datetime(2019, 3, 10, 9, 0, 0, tzinfo=UTC)
    custom_both_updated = datetime(2022, 8, 20, 16, 45, 0, tzinfo=UTC)
    org2 = Organization(name="Another Org", created_at=custom_both_created, updated_at=custom_both_updated)
    await org2.save()

    await org2.refresh_from_db()
    assert org2.created_at == custom_both_created
    assert org2.updated_at == custom_both_updated


@pytest.mark.asyncio
async def test_timestamp_bulk_create():
    custom_created = datetime(2018, 5, 15, 10, 0, 0, tzinfo=UTC)
    custom_updated = datetime(2019, 8, 20, 14, 30, 0, tzinfo=UTC)

    orgs = [
        Organization(name="Auto Org"),
        Organization(name="Manual Created", created_at=custom_created),
        Organization(name="Manual Both", created_at=custom_created, updated_at=custom_updated),
    ]

    await Organization.bulk_create(orgs)

    created_orgs = await Organization.filter(name__in=["Auto Org", "Manual Created", "Manual Both"]).order_by("name")

    assert created_orgs[0].name == "Auto Org"
    assert created_orgs[0].created_at is not None
    assert created_orgs[0].updated_at is not None

    assert created_orgs[1].name == "Manual Both"
    assert created_orgs[1].created_at == custom_created
    assert created_orgs[1].updated_at == custom_updated

    assert created_orgs[2].name == "Manual Created"
    assert created_orgs[2].created_at == custom_created
    assert created_orgs[2].updated_at is not None


@pytest.mark.asyncio
async def test_manual_timestamp_changes_tracked():
    org = await create_organization(name="Test Org")

    # Manually change created_at
    custom_time = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)
    org.created_at = custom_time

    # Should appear in changes before save
    assert "created_at" in org.changes
    assert org.changes["created_at"].new == custom_time

    await org.save()

    # After save, changes should be cleared
    assert len(org.changes) == 0

    # Manually change updated_at
    new_time = datetime(2021, 6, 15, 14, 30, 0, tzinfo=UTC)
    org.updated_at = new_time

    # Should appear in changes
    assert "updated_at" in org.changes
    assert org.changes["updated_at"].new == new_time


@pytest.mark.asyncio
async def test_automatic_timestamp_changes_not_tracked():
    org = await create_organization(name="Test Org")

    # Clear any changes from creation
    assert len(org.changes) == 0

    # Make a change that triggers automatic updated_at
    org.name = "Updated Org"

    # Should only see name change, not updated_at
    assert "name" in org.changes
    assert "updated_at" not in org.changes

    await org.save()

    # After save, no timestamp changes should be visible
    assert "updated_at" not in org.changes


@pytest.mark.asyncio
async def test_mixed_manual_and_automatic_timestamps():
    org = await create_organization(name="Test Org")

    # Manually set created_at and make another change
    org.created_at = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)
    org.name = "Updated Org"

    # Should see created_at (manual) but not updated_at (automatic)
    assert "created_at" in org.changes
    assert "name" in org.changes
    assert "updated_at" not in org.changes

    await org.save()

    # Verify timestamps were set correctly
    assert org.created_at == datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert org.updated_at > org.created_at  # Auto-set to current time


@pytest.mark.asyncio
async def test_observers_deferred_in_transactions():
    """
    Test that observers are automatically deferred until after commit when inside a transaction,
    and that after_commit callbacks run immediately when outside a transaction.
    This prevents connection reuse issues where observers receive a transaction connection
    that gets released back to the pool.
    """
    executed_callbacks: list[str | tuple[str, UUID]] = []
    created_org_ids: list[UUID] = []
    received_using_db: list[BaseDBAsyncClient | None] = []

    async def callback_from_observer(using_db: BaseDBAsyncClient):
        # Prove we can do database operations in after_commit callbacks
        if created_org_ids:
            org_id = created_org_ids[-1]
            user = await create_user(organization_id=org_id, using_db=using_db)
            executed_callbacks.append(("callback_executed", user.id))

    async def observer_with_callback(
        instance: RecordModel, changes: dict[str, Change], using_db: BaseDBAsyncClient | None = None
    ):
        # Observers can register after_commit callbacks that will execute after the observer
        created_org_ids.append(instance.global_id.record_id)
        await after_commit(callback_from_observer)
        received_using_db.append(using_db)
        executed_callbacks.append("observer_called")

    observe(RecordModelEvent.CREATE, Organization, observer_with_callback)

    try:
        # Test 1: In transaction - observer deferred until after commit
        async with transaction():
            org1 = await create_organization(name="Test Org 1")
            # Observer has not yet been called
            assert executed_callbacks == []

        # Now observer and its callback should have executed
        assert executed_callbacks[0] == "observer_called"
        assert executed_callbacks[1][0] == "callback_executed"
        user_id_1 = executed_callbacks[1][1]

        # Verify observer received a valid database connection (base_connection)
        assert received_using_db[0] is not None

        # Verify the user was actually created in the database
        user1 = await User.get(id=user_id_1)
        assert user1.organization_id == org1.id

        # Test 2: Failed transaction - neither observer nor callback should execute
        executed_callbacks.clear()
        created_org_ids.clear()
        received_using_db.clear()

        try:
            async with transaction():
                await create_organization(name="Test Org 2")
                assert executed_callbacks == []
                raise Exception("Simulated failure")
        except Exception:
            pass

        # Observer should not have been called on rollback
        assert executed_callbacks == []
        # Verify no additional user was created
        assert await User.all().count() == 1

        # Test 3: Outside transaction - observer and callback run immediately
        executed_callbacks.clear()
        created_org_ids.clear()
        received_using_db.clear()

        org3 = await create_organization(name="Test Org 3")
        # Observer runs immediately when not in a transaction
        # The after_commit callback also runs immediately (before observer completes)
        assert executed_callbacks[0][0] == "callback_executed"
        user_id_3 = executed_callbacks[0][1]
        assert executed_callbacks[1] == "observer_called"
        # When not in a transaction, using_db may be None
        assert len(received_using_db) == 1

        # Verify the user was actually created in the database
        user3 = await User.get(id=user_id_3)
        assert user3.organization_id == org3.id

    finally:
        unobserve(RecordModelEvent.CREATE, Organization, observer_with_callback)
