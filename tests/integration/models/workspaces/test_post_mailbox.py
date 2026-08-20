import pytest

from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import SubscriptionPreference
from app.models.workspaces.posts import Post, PostComment, PostMailboxEntry
from config.enums import EventAction, MailboxLabel, Sharing, SubscriptionLevel
from tests.helpers.factories import (
    create_collaborator,
    create_event,
    create_group,
    create_group_member,
    create_organization,
    create_post,
    create_post_group_mute,
    create_user,
)


async def _published_post_with_subscriber(organization, creator, subscriber):
    post = await create_post(
        creator_id=creator.id,
        organization_id=organization.id,
        title="Team Discussion",
    )
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, user_id=subscriber.id)
    await post.workspace.subscribe(subscriber.id)
    return post


@pytest.mark.asyncio
async def test_sync_creates_entries_for_subscribers_not_unsubscribed():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    subscriber = await create_user(organization_id=organization.id)
    unsubscribed_user = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(creator.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await _published_post_with_subscriber(organization, creator, subscriber)

    # Explicitly unsubscribe a user
    await create_collaborator(workspace_id=post.workspace_id, user_id=unsubscribed_user.id)
    await post.workspace.unsubscribe(unsubscribed_user.id)

    await PostMailboxEntry(post).sync()

    entries = await MailboxEntry.filter(resource_gid=str(post.global_id))
    owner_ids = {e.owner_id for e in entries}
    assert subscriber.id in owner_ids
    assert creator.id in owner_ids
    assert unsubscribed_user.id not in owner_ids


@pytest.mark.asyncio
async def test_sync_from_sets_entry_fields():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    subscriber = await create_user(organization_id=organization.id)

    post = await _published_post_with_subscriber(organization, creator, subscriber)

    await PostMailboxEntry(post).sync()

    entry = await MailboxEntry.get(resource_gid=str(post.global_id), owner_id=subscriber.id)
    assert entry.title == post.title
    assert entry.is_shared is True
    assert entry.organization_id == organization.id
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels


@pytest.mark.asyncio
async def test_sync_updates_on_new_comment():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    subscriber = await create_user(organization_id=organization.id)

    post = await _published_post_with_subscriber(organization, creator, subscriber)
    await PostMailboxEntry(post).sync()

    entry = await MailboxEntry.get(resource_gid=str(post.global_id), owner_id=subscriber.id)
    entry.label_as_read()
    entry.label_as_archived()
    await entry.save(update_fields=["labels"])

    comment = PostComment(post_id=post.id, user_id=creator.id, content="New update")
    async with post.workspace.record(EventAction.COMMENTED, recordable=comment, creator_id=creator.id) as recording:
        await comment.save(recording.using_db)

    await PostMailboxEntry(post).sync()

    await entry.refresh_from_db()
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels


@pytest.mark.asyncio
async def test_mark_as_read_survives_sync_for_the_same_comment():
    # Regression (#8816): if mark_as_read doesn't advance last_activity_at, a
    # SyncMailboxJob for the same comment that lands afterward sees a stale cursor and
    # re-surfaces UNREAD. Run the calls in the race-distinguishing order: mark_as_read,
    # then the comment's sync.
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    subscriber = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(subscriber.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await _published_post_with_subscriber(organization, creator, subscriber)
    await PostMailboxEntry(post).sync()
    await PostMailboxEntry(post).mark_as_read(subscriber)

    comment = PostComment(post_id=post.id, user_id=creator.id, content="Live update")
    async with post.workspace.record(EventAction.POST_COMMENTED, recordable=comment, creator_id=creator.id) as rec:
        await comment.save(rec.using_db)

    await PostMailboxEntry(post).mark_as_read(subscriber)
    await PostMailboxEntry(post).sync(event=rec.event, direct_recipients=[])

    entry = await MailboxEntry.get(resource_gid=str(post.global_id), owner_id=subscriber.id)
    assert entry.read_at is not None
    assert MailboxLabel.UNREAD not in entry.labels, "SyncMailboxJob clobbered the client mark_read (#8816)"


@pytest.mark.asyncio
async def test_sync_soft_deletes_on_post_deletion():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    subscriber = await create_user(organization_id=organization.id)

    post = await _published_post_with_subscriber(organization, creator, subscriber)
    await PostMailboxEntry(post).sync()

    await post.soft_delete()
    await PostMailboxEntry(post).sync()

    entries = await MailboxEntry.filter(resource_gid=str(post.global_id))
    assert len(entries) == 0

    deleted_entries = await MailboxEntry.unscoped.filter(resource_gid=str(post.global_id))
    assert all(e.is_deleted for e in deleted_entries)


@pytest.mark.asyncio
async def test_touch_syncs_single_user():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    subscriber1 = await create_user(organization_id=organization.id)
    subscriber2 = await create_user(organization_id=organization.id)

    post = await _published_post_with_subscriber(organization, creator, subscriber1)
    await create_collaborator(workspace_id=post.workspace_id, user_id=subscriber2.id)
    await post.workspace.subscribe(subscriber2.id)

    await PostMailboxEntry(post).touch(subscriber1)

    assert await MailboxEntry.get_or_none(resource_gid=str(post.global_id), owner_id=subscriber1.id) is not None
    assert await MailboxEntry.get_or_none(resource_gid=str(post.global_id), owner_id=subscriber2.id) is None


@pytest.mark.asyncio
async def test_clear_non_collaborators_removes_revoked_access():
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    subscriber = await create_user(organization_id=organization.id)

    post = await _published_post_with_subscriber(organization, creator, subscriber)
    await PostMailboxEntry(post).sync()

    assert await MailboxEntry.get_or_none(resource_gid=str(post.global_id), owner_id=subscriber.id) is not None

    post.sharing = Sharing.PRIVATE
    await post.save()
    await post.fetch_related("workspace__collaborators__user")
    collaborator = next(c for c in post.workspace.collaborators if c.user_id == subscriber.id)
    await collaborator.delete()

    await PostMailboxEntry(post).sync()

    assert await MailboxEntry.get_or_none(resource_gid=str(post.global_id), owner_id=subscriber.id) is None


@pytest.mark.asyncio
async def test_existing_row_tracks_live_content_for_below_all_owner():
    # Cross-resource check of the mentioned-then-quiet fix (shares _update_inbox_rows_for_event
    # / InboxUpdate.for_event with chat): a post collaborator below ALL via a global
    # RELEVANT_ONLY preference, pulled in by a mention, keeps their row current on
    # later non-mention comments without re-bumping to unread once read.
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    observer = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(observer.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})

    post = await create_post(creator_id=creator.id, organization_id=organization.id, title="Team Discussion")
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, user_id=observer.id)

    mention_comment = PostComment(post_id=post.id, user_id=creator.id, content="ping @observer")
    async with post.workspace.record(EventAction.COMMENTED, recordable=mention_comment, creator_id=creator.id) as rec:
        await mention_comment.save(rec.using_db)
    await PostMailboxEntry(post).sync(event=rec.event, direct_recipients=[observer])

    entry = await MailboxEntry.get(resource_gid=str(post.global_id), owner_id=observer.id)
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels
    await PostMailboxEntry(post).mark_as_read(observer)

    quiet_comment = PostComment(post_id=post.id, user_id=creator.id, content="quiet follow up")
    async with post.workspace.record(EventAction.COMMENTED, recordable=quiet_comment, creator_id=creator.id) as rec2:
        await quiet_comment.save(rec2.using_db)
    await PostMailboxEntry(post).sync(event=rec2.event, direct_recipients=[])

    await entry.refresh_from_db()
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD not in entry.labels


@pytest.mark.asyncio
async def test_assignment_force_surfaces_below_all_assignee():
    # Assignment is a direct ask: the assignee is force-surfaced (INBOX + UNREAD) like an
    # @mention, even when their level (RELEVANT_ONLY) would keep the post out of their inbox and
    # the ASSIGNED event creates no comment for the content gate to see. Shares the
    # direct-recipient path with email threads.
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    assignee = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(assignee.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})

    post = await create_post(creator_id=creator.id, organization_id=organization.id, title="Do this")
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, user_id=assignee.id)

    event = await create_event(post.workspace, creator_id=creator.id, action=EventAction.ASSIGNED)
    await PostMailboxEntry(post).sync(event=event, direct_recipients=[assignee])

    entry = await MailboxEntry.get(resource_gid=str(post.global_id), owner_id=assignee.id)
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels


@pytest.mark.asyncio
async def test_org_wide_post_event_reaches_non_collaborators_by_tier():
    # An org-wide post reaches non-collaborator org members by their Post tier:
    # Relevant stays out of the inbox; Broadcasts and All get a row.
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    relevant_user = await create_user(organization_id=organization.id)
    broadcasts_user = await create_user(organization_id=organization.id)
    all_user = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(relevant_user.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})
    await SubscriptionPreference.update_for(broadcasts_user.id, {Post.record_type: SubscriptionLevel.BROADCASTS})
    await SubscriptionPreference.update_for(all_user.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await create_post(
        creator_id=creator.id, organization_id=organization.id, title="All hands", sharing=Sharing.ORGANIZATION
    )
    await post.fetch_related("workspace")
    event = await create_event(post.workspace, creator_id=creator.id, action=EventAction.POST_CREATED)
    await PostMailboxEntry(post).sync(event=event, direct_recipients=[])

    owner_ids = {e.owner_id for e in await MailboxEntry.filter(resource_gid=str(post.global_id))}
    assert relevant_user.id not in owner_ids
    assert broadcasts_user.id in owner_ids
    assert all_user.id in owner_ids


@pytest.mark.asyncio
async def test_other_group_post_event_reaches_only_all_non_members():
    # A grouped post still broadcasts org-wide for the ALL tier, but Broadcasts and
    # Relevant non-members stay out (in-group reach is the members' path, below).
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    group = await create_group(organization_id=organization.id)
    await create_group_member(group_id=group.id, user_id=creator.id)

    relevant_user = await create_user(organization_id=organization.id)
    broadcasts_user = await create_user(organization_id=organization.id)
    all_user = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(relevant_user.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})
    await SubscriptionPreference.update_for(broadcasts_user.id, {Post.record_type: SubscriptionLevel.BROADCASTS})
    await SubscriptionPreference.update_for(all_user.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await create_post(
        creator_id=creator.id,
        organization_id=organization.id,
        title="Group update",
        sharing=Sharing.ORGANIZATION,
        group_id=group.id,
    )
    await post.fetch_related("workspace")
    event = await create_event(post.workspace, creator_id=creator.id, action=EventAction.POST_CREATED)
    await PostMailboxEntry(post).sync(event=event, direct_recipients=[])

    owner_ids = {e.owner_id for e in await MailboxEntry.filter(resource_gid=str(post.global_id))}
    assert relevant_user.id not in owner_ids
    assert broadcasts_user.id not in owner_ids
    assert all_user.id in owner_ids


@pytest.mark.asyncio
async def test_group_member_post_event_reaches_members_and_respects_mute():
    # Group members reach the inbox via membership; a PostGroupMute opts a member out.
    organization = await create_organization()
    creator = await create_user(organization_id=organization.id)
    group = await create_group(organization_id=organization.id)
    await create_group_member(group_id=group.id, user_id=creator.id)

    member = await create_user(organization_id=organization.id)
    muted_member = await create_user(organization_id=organization.id)
    await create_group_member(group_id=group.id, user_id=member.id)
    await create_group_member(group_id=group.id, user_id=muted_member.id)

    post = await create_post(
        creator_id=creator.id,
        organization_id=organization.id,
        title="Group update",
        sharing=Sharing.ORGANIZATION,
        group_id=group.id,
    )
    await post.fetch_related("workspace")
    await create_post_group_mute(user_id=muted_member.id, group_id=group.id)

    event = await create_event(post.workspace, creator_id=creator.id, action=EventAction.POST_CREATED)
    await PostMailboxEntry(post).sync(event=event, direct_recipients=[])

    owner_ids = {e.owner_id for e in await MailboxEntry.filter(resource_gid=str(post.global_id))}
    assert member.id in owner_ids
    assert muted_member.id not in owner_ids
