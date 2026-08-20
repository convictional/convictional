import pytest

from app.models.collaboration.workspace import (
    Collaborator,
    SubscriberResolver,
    Subscription,
    SubscriptionPreference,
)
from app.models.workspaces.posts import Post
from config.enums import EventAction, SubscriptionLevel, SubscriptionSource
from tests.helpers.factories import (
    create_collaborator,
    create_event,
    create_group,
    create_group_member,
    create_post,
    create_post_group_mute,
    create_user,
)


@pytest.mark.asyncio
async def test_group_member_added_becomes_post_collaborator():
    creator = await create_user()
    group = await create_group(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    new_member = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(new_member.id, {Post.record_type: SubscriptionLevel.ALL})
    await create_group_member(group_id=group.id, user_id=new_member.id)

    collaborator = await Collaborator.get_or_none(workspace_id=post.workspace_id, user_id=new_member.id)
    assert collaborator is not None

    # No subscription row written — fallback chain handles delivery decisions.
    subscription = await Subscription.get_or_none(workspace_id=post.workspace_id, subscriber_id=new_member.id)
    assert subscription is None
    assert new_member in await SubscriberResolver(workspace=post.workspace).resolve()


@pytest.mark.asyncio
async def test_everyone_post_subscribes_organization_members():
    # "Everyone" posts opt into notification_policy.broadcasts_to_organization;
    # bystanders with global ALL enter the candidate set without a Collaborator row.
    creator = await create_user()
    bystander = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(bystander.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await post.fetch_related("workspace")

    assert post.group_id is None
    assert post.sharing.is_organization
    assert await Collaborator.get_or_none(workspace_id=post.workspace_id, user_id=bystander.id) is None
    assert bystander in await SubscriberResolver(workspace=post.workspace).resolve()


@pytest.mark.asyncio
async def test_group_post_does_not_subscribe_bystanders_without_global_all():
    # Default global preference is RELEVANT_ONLY: a bystander outside the group
    # stays out of the candidate set's effective subscribers.
    creator = await create_user()
    bystander = await create_user(organization_id=creator.organization_id)
    group = await create_group(organization_id=creator.organization_id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    assert post.group_id == group.id
    assert post.sharing.is_organization
    assert await Collaborator.get_or_none(workspace_id=post.workspace_id, user_id=bystander.id) is None
    assert bystander not in await SubscriberResolver(workspace=post.workspace).resolve()


@pytest.mark.asyncio
async def test_group_post_subscribes_bystanders_with_global_all():
    # Org-shared posts broadcast to organization regardless of group scoping.
    # A non-member with global Posts=ALL gets an inbox entry; per-group override
    # is the opt-out mechanism (covered in the next test).
    creator = await create_user()
    bystander = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(bystander.id, {Post.record_type: SubscriptionLevel.ALL})
    group = await create_group(organization_id=creator.organization_id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    assert await Collaborator.get_or_none(workspace_id=post.workspace_id, user_id=bystander.id) is None
    assert bystander in await SubscriberResolver(workspace=post.workspace).resolve()


@pytest.mark.asyncio
async def test_group_member_receives_grouped_post_with_default_global_preference():
    # Membership is itself a relevance signal: a group member with the default
    # global preference (RELEVANT_ONLY) still gets grouped posts in their inbox.
    creator = await create_user()
    member = await create_user(organization_id=creator.organization_id)
    group = await create_group(organization_id=creator.organization_id)
    await create_group_member(group_id=group.id, user_id=member.id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    assert member in await SubscriberResolver(workspace=post.workspace).resolve()
    state = await SubscriberResolver(workspace=post.workspace).state_for(member.id)
    assert state.level == SubscriptionLevel.ALL
    assert state.source == SubscriptionSource.GROUP_MEMBERSHIP


@pytest.mark.asyncio
async def test_group_member_mute_overrides_global_all():
    # Mute beats global ALL: the in-group mute is decisive for members. A user
    # with global ALL who explicitly mutes a group they're in should NOT see
    # posts to that group.
    creator = await create_user()
    member = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(member.id, {Post.record_type: SubscriptionLevel.ALL})
    group = await create_group(organization_id=creator.organization_id)
    await create_group_member(group_id=group.id, user_id=member.id)
    await create_post_group_mute(user_id=member.id, group_id=group.id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    assert member not in await SubscriberResolver(workspace=post.workspace).resolve()
    state = await SubscriberResolver(workspace=post.workspace).state_for(member.id)
    assert state.level == SubscriptionLevel.RELEVANT_ONLY
    assert state.source == SubscriptionSource.GROUP_MEMBERSHIP


@pytest.mark.asyncio
async def test_creator_in_muted_group_still_receives_own_posts():
    # Creator rule wins over the membership tier — muting a group you posted to
    # shouldn't drop you out of your own thread.
    creator = await create_user()
    group = await create_group(organization_id=creator.organization_id)
    await create_group_member(group_id=group.id, user_id=creator.id)
    await create_post_group_mute(user_id=creator.id, group_id=group.id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    state = await SubscriberResolver(workspace=post.workspace).state_for(creator.id)
    assert state.level == SubscriptionLevel.ALL
    assert state.source == SubscriptionSource.CREATOR


@pytest.mark.asyncio
async def test_creator_implicitly_subscribed_at_all():
    # The creator of a workspace resource is implicitly resolved to ALL by the
    # subscriber resolver — without materializing a Subscription row — so that
    # replies on a post you created reach you regardless of group/global defaults.
    # An explicit per-resource row still wins (downgrade or upgrade), keeping
    # "I deliberately muted this thread" working.
    creator = await create_user()

    # Blanket global preference for Posts set to RELEVANT_ONLY shouldn't drop
    # the creator out of their own thread.
    await SubscriptionPreference.update_for(creator.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await post.fetch_related("workspace")

    assert await Subscription.get_or_none(workspace_id=post.workspace_id, subscriber_id=creator.id) is None
    assert creator in await SubscriberResolver(workspace=post.workspace).resolve()

    state = await SubscriberResolver(workspace=post.workspace).state_for(creator.id)
    assert state.level == SubscriptionLevel.ALL
    assert state.source == SubscriptionSource.CREATOR

    # Explicit per-resource mute overrides the implicit creator rule.
    await post.workspace.unsubscribe(creator.id)
    assert creator not in await SubscriberResolver(workspace=post.workspace).resolve()
    state = await SubscriberResolver(workspace=post.workspace).state_for(creator.id)
    assert state.level == SubscriptionLevel.RELEVANT_ONLY
    assert state.source == SubscriptionSource.RESOURCE


@pytest.mark.asyncio
async def test_broadcasts_preference_receives_everyone_post():
    # A bystander on BROADCASTS gets posts addressed to Everyone (no group) but
    # not posts scoped to groups they haven't joined.
    creator = await create_user()
    bystander = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(bystander.id, {Post.record_type: SubscriptionLevel.BROADCASTS})

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await post.fetch_related("workspace")

    assert post.group_id is None
    assert bystander in await SubscriberResolver(workspace=post.workspace).resolve()
    state = await SubscriberResolver(workspace=post.workspace).state_for(bystander.id)
    assert state.level == SubscriptionLevel.ALL
    assert state.source == SubscriptionSource.GLOBAL


@pytest.mark.asyncio
async def test_broadcasts_preference_skips_non_member_group_post():
    # BROADCASTS only opens the door for Everyone-posts. Non-member group posts
    # still fall through to RELEVANT_ONLY for non-members.
    creator = await create_user()
    bystander = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(bystander.id, {Post.record_type: SubscriptionLevel.BROADCASTS})
    group = await create_group(organization_id=creator.organization_id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    assert bystander not in await SubscriberResolver(workspace=post.workspace).resolve()
    state = await SubscriberResolver(workspace=post.workspace).state_for(bystander.id)
    assert state.level == SubscriptionLevel.RELEVANT_ONLY
    assert state.source == SubscriptionSource.GLOBAL


@pytest.mark.asyncio
async def test_broadcasts_preference_does_not_override_group_mute():
    # Membership tier is decisive — a muted member stays muted even when their
    # global pref is BROADCASTS.
    creator = await create_user()
    member = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(member.id, {Post.record_type: SubscriptionLevel.BROADCASTS})
    group = await create_group(organization_id=creator.organization_id)
    await create_group_member(group_id=group.id, user_id=member.id)
    await create_post_group_mute(user_id=member.id, group_id=group.id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    assert member not in await SubscriberResolver(workspace=post.workspace).resolve()


@pytest.mark.asyncio
async def test_broadcasts_bystander_source_attribution_via_hot_path():
    # Hot path (resolve_with_sources) and cold path (state_for) must agree on
    # source attribution for a BROADCASTS bystander on an org-wide post: GLOBAL,
    # since their global preference is what resolved them to ALL.
    creator = await create_user()
    bystander = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(bystander.id, {Post.record_type: SubscriptionLevel.BROADCASTS})

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await post.fetch_related("workspace")
    assert post.group_id is None

    resolver = SubscriberResolver(workspace=post.workspace)
    subscribers = await resolver.resolve_with_sources()
    bystander_entry = next(((u, s) for u, s in subscribers if u.id == bystander.id), None)
    assert bystander_entry is not None
    assert bystander_entry[1] == SubscriptionSource.GLOBAL


@pytest.mark.asyncio
async def test_member_with_relevant_only_global_pref_attributes_to_membership():
    # Regression: a member with a non-ALL global preference (e.g. RELEVANT_ONLY)
    # resolves to ALL via the membership tier, not via global. Source should
    # report GROUP_MEMBERSHIP, not GLOBAL — global isn't what put them at ALL.
    creator = await create_user()
    member = await create_user(organization_id=creator.organization_id)
    # update_for creates a row at RELEVANT_ONLY; explicit to make the intent obvious.
    await SubscriptionPreference.update_for(member.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})
    group = await create_group(organization_id=creator.organization_id)
    await create_group_member(group_id=group.id, user_id=member.id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    resolver = SubscriberResolver(workspace=post.workspace)
    subscribers = await resolver.resolve_with_sources()
    member_entry = next(((u, s) for u, s in subscribers if u.id == member.id), None)
    assert member_entry is not None
    assert member_entry[1] == SubscriptionSource.GROUP_MEMBERSHIP


@pytest.mark.asyncio
async def test_group_member_removal_preserves_subscription_rows():
    creator = await create_user()
    member = await create_user(organization_id=creator.organization_id)
    group = await create_group(organization_id=creator.organization_id)
    group_member = await create_group_member(group_id=group.id, user_id=member.id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")

    # Member explicitly clicks subscribe.
    await post.workspace.subscribe(member.id)
    row = await Subscription.get(workspace_id=post.workspace_id, subscriber_id=member.id)
    assert row.wants_all

    # Group removal does not touch the explicit row.
    await group_member.delete()
    await row.refresh_from_db()
    assert row.wants_all


@pytest.mark.asyncio
async def test_resolve_for_push_pushes_post_creator_and_assignee_on_reply():
    # A reply/comment on a post pushes its creator and assignee (POST_COMMENTED),
    # even without an explicit opt-in. A post subscriber (global Posts=ALL) who
    # is neither — and isn't a collaborator — does not push.
    creator = await create_user()
    assignee = await create_user(organization_id=creator.organization_id)
    bystander = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(bystander.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, user_id=assignee.id)
    post.workspace.assignee_id = assignee.id
    await post.workspace.save()

    commenter = await create_user(organization_id=creator.organization_id)
    event = await create_event(post.workspace, creator_id=commenter.id, action=EventAction.POST_COMMENTED)

    resolver = SubscriberResolver(workspace=post.workspace)
    pushed = {
        u.id for u in await resolver.resolve_for_push(event, mention_user_ids=set(), exclude_user_id=commenter.id)
    }
    assert pushed == {creator.id, assignee.id}
    # The global-ALL subscriber is an effective subscriber (inbox/email) but is
    # not pushed for a post.
    assert bystander in await resolver.resolve()


@pytest.mark.asyncio
async def test_resolve_for_push_empty_for_plain_post_created():
    # Publishing a post (POST_CREATED) pushes no one — not the creator, not a
    # global-ALL subscriber. They're notified via inbox/email only.
    creator = await create_user()
    bystander = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(bystander.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await post.fetch_related("workspace")
    event = await create_event(post.workspace, creator_id=creator.id, action=EventAction.POST_CREATED)

    resolver = SubscriberResolver(workspace=post.workspace)
    assert creator in await resolver.resolve()
    assert await resolver.resolve_for_push(event, mention_user_ids=set()) == []


@pytest.mark.asyncio
async def test_resolve_for_push_skips_subscriber_who_is_not_creator_or_assignee():
    # Group membership plus a global Posts=ALL resolves a member to an effective
    # subscriber (inbox), but a comment on a post pushes only its creator and
    # assignee — so this subscriber (neither, even un-muted) isn't pushed.
    creator = await create_user()
    member = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(member.id, {Post.record_type: SubscriptionLevel.ALL})
    group = await create_group(organization_id=creator.organization_id)
    await create_group_member(group_id=group.id, user_id=member.id)

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await post.fetch_related("workspace")
    event = await create_event(post.workspace, creator_id=creator.id, action=EventAction.POST_COMMENTED)

    resolver = SubscriberResolver(workspace=post.workspace)
    assert member in await resolver.resolve()
    pushed = {u.id for u in await resolver.resolve_for_push(event, mention_user_ids=set(), exclude_user_id=creator.id)}
    assert member.id not in pushed
