from app.channels.base import Channel, ChannelRouter
from app.channels.dependencies import is_current_user_authorized
from app.models.collaboration.mailbox import (
    MailboxViewCache,
    MailboxViewCacheData,
    MailboxViewIdentifier,
    MailboxViewSource,
)
from infra.messaging import Topic

router = ChannelRouter()


@router.on_subscribe("mailbox_view")
async def mailbox_view_subscribe(channel: Channel):
    """
    Handle subscription to a mailbox view channel.

    The new-messages baseline comes from the server's own cache record (`cached_at` + the entry ids
    it holds), never from a client param — the client only names which view it's on. The cache is the
    single source of truth: a reconnect after a cache-miss generation can't drive a spurious re-rank,
    and the banner count can't go stale against what the client thinks it cached (#8330). Every path
    that wants a fresh generation (refresh, view update) deletes the cache first, so a present cache
    is always reusable.
    """
    view_id_str = channel.get_param("view_id")
    if not view_id_str:
        await channel.reject("Missing view_id parameter")
        return

    if not await is_current_user_authorized(channel):
        return

    await channel.accept()

    identifier = MailboxViewIdentifier.from_string(view_id_str)
    if not identifier:
        return

    # A None source means a saved view that doesn't exist (or isn't this user's) — leave it
    # alone. A template always resolves, so a missing template cache falls through to
    # regeneration below, same as a saved view with an expired cache.
    source = await MailboxViewSource.resolve(identifier, channel.current_user)
    if not source:
        return

    cache_data = await source.read_cache()
    await _handle_cache_check(channel, cache_data, view_id_str)


async def _handle_cache_check(
    channel: Channel,
    cache_data: MailboxViewCacheData | None,
    view_id_str: str,
) -> None:
    """If cache is still valid, check for new entries. Otherwise, clear and regenerate."""
    if cache_data:
        await _handle_cached_view_subscribe(channel, view_id_str, cache_data)
    else:
        await _broadcast_cache_expired_and_regenerate(channel, view_id_str)


async def _broadcast_cache_expired_and_regenerate(channel: Channel, view_id_str: str) -> None:
    """Broadcast cache expiry to clear old sections, then trigger regeneration."""
    topic = Topic("mailbox_view", view_id=view_id_str, user_id=str(channel.current_user.id))
    # `kind` tags this for the JSON consumer's discriminated union (see
    # app/routers/api/mailbox_views.py). `cache_expired` is kept for the legacy untagged
    # fallback path in `_classify_broadcast`.
    await topic.broadcast(kind="cache_expired", cache_expired=True)
    await topic.broadcast(action="start_generation")


async def _handle_cached_view_subscribe(channel: Channel, view_id: str, cache_data: MailboxViewCacheData):
    """Handle subscription for a cached mailbox view - check for new entries."""
    topic = Topic("mailbox_view", view_id=view_id, user_id=str(channel.current_user.id))

    # A client that boosted-navigated away mid-generation still holds generating=true: the
    # generation's own `complete` broadcast fired to no one while it was unsubscribed, and the
    # index query never re-validates (staleTime:Infinity + refetchOnMount:false). The completed
    # result is cached now, so re-announce `complete` on (re)subscribe to settle the stranded
    # client. An in-progress partial (generating=True) is deliberately skipped — its live session
    # is still streaming to this topic (or, if the task died, only a refresh recovers it).
    if not cache_data.generating:
        await topic.broadcast(complete=True)

    new_count = await MailboxViewCache.count_new_entries(
        user=channel.current_user,
        since=cache_data.cached_at,
        exclude_entry_ids=set(cache_data.entry_ids),
    )

    if new_count > 0:
        # `kind` tags this for the JSON consumer's discriminated union (see
        # app/routers/api/mailbox_views.py); `new_messages_count` is also kept for the
        # untagged fallback path in `_classify_broadcast`.
        await topic.broadcast(kind="new_messages", new_messages_count=new_count, view_id=view_id)
