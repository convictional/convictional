import pytest

from app.models.collaboration.workspace import (
    SubscriberResolver,
    Subscription,
    SubscriptionLevel,
    SubscriptionPreference,
)
from app.models.workspaces.posts import Post
from tests.helpers.factories import create_group, create_group_member, create_post, create_user


@pytest.mark.asyncio
async def test_explicit_ignored_row_beats_group_fallback():
    """An explicit IGNORED row beats the group preference fallback and
    survives post-save signals."""

    creator = await create_user()
    member = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(member.id, {Post.record_type: SubscriptionLevel.ALL})
    group = await create_group(organization_id=creator.organization_id)
    await create_group_member(group_id=group.id, user_id=creator.id)
    await create_group_member(group_id=group.id, user_id=member.id)

    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        group_id=group.id,
    )
    await post.fetch_related("workspace")

    # No auto-subscribe row written for the group member; effective subscription
    # comes from the global preference fallback set above to ALL.
    assert await Subscription.get_or_none(workspace_id=post.workspace_id, subscriber_id=member.id) is None
    assert member in await SubscriberResolver(workspace=post.workspace).resolve()

    # Member explicitly unsubscribes — row written with level=IGNORED.
    await post.workspace.unsubscribe(member.id)
    row = await Subscription.get(workspace_id=post.workspace_id, subscriber_id=member.id)
    assert row.level == SubscriptionLevel.RELEVANT_ONLY
    assert member not in await SubscriberResolver(workspace=post.workspace).resolve()

    # Post is edited, triggering the post_save signal. The explicit IGNORED row survives.
    post.title = "Updated title"
    await post.save(update_fields=["title"])

    await row.refresh_from_db()
    assert row.level == SubscriptionLevel.RELEVANT_ONLY
    assert member not in await SubscriberResolver(workspace=post.workspace).resolve()
