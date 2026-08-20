"""Scenario builders for the notifications suite.

A Scenario assembles a resource plus the named people around it — each declared in one
line with the relationship/preference that defines them (a level, a device, assignee, a
group mute) — then fires an event and asserts each person's outcome.

The generic `Scenario` base owns everything that is the same for every resource: adding
people, setting subscription levels, granting devices, and asserting outcomes. Each
resource subclass supplies only the two things that are irreducibly resource-specific:
how the resource is created, and how its event is fired (through the visible `harness`
HTTP adapter). Scenarios do setup and reading only — outcomes always come from real
MailboxEntry / push-ledger rows.
"""

from typing import ClassVar
from uuid import UUID

from app.models.accounts import Group, User
from app.models.collaboration.workspace import Subscription, SubscriptionPreference, WorkspaceMixin
from app.models.workspaces.chat import Chat
from app.models.workspaces.email.thread import EmailThread
from app.models.workspaces.goals import Goal
from app.models.workspaces.posts import Post
from config.enums import SubscriptionLevel
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_chat,
    create_collaborator,
    create_email_thread,
    create_goal,
    create_group,
    create_group_member,
    create_post,
    create_post_group_mute,
    create_push_subscription,
    create_user,
)
from tests.integration.notifications import harness


class Scenario:
    """Generic setup + assertion, shared by every resource."""

    record_type: ClassVar[str]  # the resource's SubscriptionPreference key

    def __init__(self, client: AppClient, organization_id: UUID):
        self.client = client
        self.organization_id = organization_id
        self.resource: WorkspaceMixin | None = None
        self.people: dict[str, User] = {}

    async def _person(self, key: str) -> User:
        # `name` is the mention handle — `comment(mentioning=key)` builds `@[key]` from it.
        user = await create_user(name=key, organization_id=self.organization_id, time_zone="UTC")
        self.people[key] = user
        return user

    async def add(
        self,
        key: str,
        *,
        level: SubscriptionLevel | None = None,
        assignee: bool = False,
        collaborator: bool = True,
        device: bool = True,
    ) -> User:
        """Add one person. Each keyword is a trait; the defaults make a plain
        collaborator with a device."""
        user = await self._person(key)
        # resource is None only in the pre-create flow (the `create()` event, where people
        # are org members added before the post exists) — there's nothing to attach to yet.
        if collaborator and self.resource is not None:
            await create_collaborator(workspace_id=self.resource.workspace_id, user_id=user.id)
        if assignee:
            assert self.resource is not None
            self.resource.workspace.assignee_id = user.id
            await self.resource.workspace.save()
        if level is not None:
            await SubscriptionPreference.update_for(user.id, {self.record_type: level})
        if device:
            await create_push_subscription(user_id=user.id)
        return user

    async def archive(self, *, by: str) -> None:
        """Archive one person's own mailbox row, off the inbox surface — the precondition
        for testing how a later event treats an already-archived recipient."""
        assert self.resource is not None
        await harness.emit_mailbox_archive(self.client, self.resource, self.people[by])

    async def expect(self, **expected: tuple) -> None:
        assert self.resource is not None
        await self.expect_for(self.resource, **expected)

    async def expect_for(self, resource: WorkspaceMixin, **expected: tuple) -> None:
        """Assert outcomes against a specific resource — for tests that touch more than one
        (e.g. a subgoal and its parent), where `self.resource` isn't the only surface."""
        personas = {key: self.people[key] for key in expected}
        harness.assert_outcomes(expected, await harness.outcomes(resource, personas))


class PostScenario(Scenario):
    record_type = Post.record_type

    def __init__(self, client: AppClient, organization_id: UUID, creator: User):
        super().__init__(client, organization_id)
        self.creator = creator
        self.group: Group | None = None
        self.people["creator"] = creator

    @classmethod
    async def new(cls, client: AppClient, *, group: bool = False) -> "PostScenario":
        """A scenario with a creator (and optional group) but no post yet — for the
        `create()` event, where the post is born from the event itself."""
        organization_id = (await client.get_default_user()).organization_id
        creator = await create_user(name="Creator", organization_id=organization_id, time_zone="UTC")
        await create_push_subscription(user_id=creator.id)
        scenario = cls(client, organization_id, creator)
        if group:
            scenario.group = await create_group(organization_id=organization_id)
            await create_group_member(group_id=scenario.group.id, user_id=creator.id)
        return scenario

    @classmethod
    async def published(cls, client: AppClient, *, group: bool = False, title: str = "Post") -> "PostScenario":
        scenario = await cls.new(client, group=group)
        group_id = scenario.group.id if scenario.group else None
        scenario.resource = await create_post(
            creator_id=scenario.creator.id, organization_id=scenario.organization_id, title=title, group_id=group_id
        )
        await scenario.resource.fetch_related("workspace")
        return scenario

    async def add(self, key: str, *, in_group: bool = False, muted: bool = False, **traits) -> User:
        user = await super().add(key, **traits)
        if in_group:
            assert self.group is not None
            await create_group_member(group_id=self.group.id, user_id=user.id)
        if muted:
            assert self.group is not None
            await create_post_group_mute(user_id=user.id, group_id=self.group.id)
        return user

    async def comment(self, *, by: str, mentioning: str | None = None, parent_id: str | None = None) -> str:
        """Add a comment (or, with `parent_id`, a reply to one). Returns the new
        comment's id so a test can thread a reply onto a thread starter."""
        assert isinstance(self.resource, Post)
        content = f"thoughts? @[{self.people[mentioning].name}]" if mentioning else "what do you think?"
        return await harness.emit_post_commented(
            self.client, self.resource, self.people[by], content=content, parent_id=parent_id
        )

    async def assign(self, *, assignee: str, by: str) -> None:
        assert self.resource is not None
        await harness.emit_assigned(self.client, self.resource, self.people[by], self.people[assignee])

    async def create(self, *, title: str = "All hands") -> None:
        self.resource = await harness.emit_post_created(self.client, self.creator, title=title)


class ChatScenario(Scenario):
    record_type = Chat.record_type

    @classmethod
    async def new(cls, client: AppClient, *, channel: bool = False) -> "ChatScenario":
        organization_id = (await client.get_default_user()).organization_id
        scenario = cls(client, organization_id)
        group_id = None
        if channel:
            group = await create_group(organization_id=organization_id)
            group_id = group.id
        scenario.resource = await create_chat(
            organization_id=organization_id, group_id=group_id, title="Engineering" if channel else None
        )
        await scenario.resource.fetch_related("workspace")
        return scenario

    async def message(self, *, by: str, mentioning: str | None = None) -> None:
        assert self.resource is not None
        content = f"status @[{self.people[mentioning].name}]?" if mentioning else "hey team"
        await harness.emit_chat_message(self.client, self.resource, self.people[by], content=content)


class GoalScenario(Scenario):
    record_type = Goal.record_type

    def __init__(self, client: AppClient, organization_id: UUID, owner: User):
        super().__init__(client, organization_id)
        self.owner = owner
        self.group: Group | None = None
        self.people["owner"] = owner

    @classmethod
    async def new(cls, client: AppClient, *, group: bool = False, title: str = "Ship Q3") -> "GoalScenario":
        """A new, active goal owned by `owner` (a group member when `group`). A goal's collaborators
        are its owner and its group's members (the `ensure_goal_collaborators` signal), so a group
        goal reaches the whole group; a groupless goal reaches only who is added as a collaborator."""
        organization_id = (await client.get_default_user()).organization_id
        owner = await create_user(name="Owner", organization_id=organization_id, time_zone="UTC")
        await create_push_subscription(user_id=owner.id)
        scenario = cls(client, organization_id, owner)
        if group:
            scenario.group = await create_group(organization_id=organization_id)
            await create_group_member(group_id=scenario.group.id, user_id=owner.id)
        scenario.resource = await scenario._make_goal(title=title)
        return scenario

    async def _make_goal(self, *, title: str, parent_id: UUID | None = None) -> Goal:
        goal = await create_goal(
            organization_id=self.organization_id,
            creator_id=self.owner.id,
            owner_id=self.owner.id,
            title=title,
            group_id=self.group.id if self.group else None,
            parent_id=parent_id,
        )
        await goal.fetch_related("workspace")
        return goal

    async def make_subgoal(self, *, title: str = "Subgoal") -> Goal:
        """A subgoal is its own goal (own workspace, own inbox row); events on it do not fan
        onto the parent. Shares the parent's group, so the group's members collaborate on both."""
        assert self.resource is not None
        return await self._make_goal(title=title, parent_id=self.resource.id)

    async def add(self, key: str, *, in_group: bool = False, **traits) -> User:
        user = await super().add(key, **traits)
        if in_group:
            assert self.group is not None
            await create_group_member(group_id=self.group.id, user_id=user.id)
        return user

    async def subscribe_relevant(self, key: str) -> None:
        """Dial one person down to RELEVANT_ONLY via an explicit per-goal subscription — what the
        goal's SubscriptionBell set to "Relevant to me" does. For a group member (who defaults to
        ALL) this is one of two opt-downs, the other being the global "Goals" preference."""
        assert self.resource is not None
        await Subscription.create(
            subscriber_id=self.people[key].id,
            workspace_id=self.resource.workspace_id,
            level=SubscriptionLevel.RELEVANT_ONLY,
        )

    async def comment(self, *, by: str, mentioning: str | None = None, parent_id: str | None = None) -> str:
        assert isinstance(self.resource, Goal)
        content = f"thoughts? @[{self.people[mentioning].name}]" if mentioning else "what do you think?"
        return await harness.emit_goal_commented(
            self.client, self.resource, self.people[by], content=content, parent_id=parent_id
        )

    async def post_update(self, *, by: str) -> None:
        assert isinstance(self.resource, Goal)
        await harness.emit_goal_update_posted(self.client, self.resource, self.people[by])

    async def request_update(self, *, by: str) -> None:
        assert isinstance(self.resource, Goal)
        await harness.emit_goal_update_requested(self.client, self.resource, self.people[by])

    async def complete(self, *, by: str) -> None:
        assert isinstance(self.resource, Goal)
        await harness.emit_goal_closed(self.client, self.resource, self.people[by], is_completed=True)

    async def edit_title(self, *, by: str, title: str) -> None:
        assert isinstance(self.resource, Goal)
        await harness.emit_goal_edited(self.client, self.resource, self.people[by], title=title)

    async def mark_read(self, *, by: str) -> None:
        assert self.resource is not None
        await harness.emit_mailbox_mark_read(self.client, self.resource, self.people[by])


class EmailThreadScenario(Scenario):
    record_type = EmailThread.record_type

    def __init__(self, client: AppClient, organization_id: UUID, creator: User):
        super().__init__(client, organization_id)
        self.creator = creator
        self.people["creator"] = creator

    @classmethod
    async def new(cls, client: AppClient) -> "EmailThreadScenario":
        organization_id = (await client.get_default_user()).organization_id
        creator = await create_user(name="Creator", organization_id=organization_id, time_zone="UTC")
        await create_push_subscription(user_id=creator.id)
        scenario = cls(client, organization_id, creator)
        scenario.resource = await create_email_thread(creator_id=creator.id, organization_id=organization_id)
        await scenario.resource.fetch_related("workspace")
        # Publish the thread so the creator has a mailbox entry before any comment, exactly as
        # production does (a thread is born from a message/draft that publishes it). Without a
        # prior entry, a comment would create the creator's owner-row fresh, and the email
        # read-state gate — which mirrors Gmail's read state and can't see a brand-new comment on
        # a new entry — would land it read instead of unread.
        await scenario.resource.publish()
        return scenario

    async def comment(self, *, by: str, mentioning: str | None = None, reply_to_id: str | None = None) -> str:
        """Add a comment (or, with `reply_to_id`, a reply to one). Returns the new
        comment's id so a test can thread a reply onto a thread starter."""
        assert self.resource is not None
        content = f"thoughts? @[{self.people[mentioning].name}]" if mentioning else "a reply, no mention"
        return await harness.emit_email_thread_comment(
            self.client, self.resource, self.people[by], content=content, reply_to_id=reply_to_id
        )
