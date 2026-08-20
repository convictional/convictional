"""JSON-mode channel handler tests for mailbox_sync and mailbox_view streams.

These exercise the EventMessage payloads emitted by the React-facing handlers
in app/routers/api/mailbox_entries.py and app/routers/api/mailbox_views.py.
The HTML handlers stay in place — both fire on the same broadcast (dual dispatch).
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.collaboration.mailbox import Mailbox, MailboxEntry, MailboxView, MailboxViewCache
from app.presenters.mailbox_view import ViewSection
from app.routers.api.mailbox_views import ViewGenerationSession, view_generation_manager
from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.cache import cache
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import (
    create_email_message,
    create_goal,
    create_mailbox_view,
    create_user,
)


async def _seed_cached_view(user_id, organization_id) -> tuple[MailboxView, datetime]:
    """Create a view + write an in-progress (generating) cache so the subscribe stays quiet.

    Without a cache, mailbox_view_subscribe fires start_generation, which
    mailbox_view_json_broadcast picks up and (with too few entries) ends up broadcasting
    an error — which leaks into our JSON broadcast assertions. A cache makes the subscribe
    take the banner-check path instead. It's written `generating=True` (an in-progress
    partial) specifically so the subscribe does NOT re-announce `complete`: a *settled* cache
    now emits `complete` on subscribe to recover a client stranded mid-generation (see
    _handle_cached_view_subscribe), which would otherwise front-run the manually-driven events
    each test below asserts on. These tests simulate an in-flight generation streaming its own
    section/complete events, so a generating partial is the honest state.
    """
    view = await create_mailbox_view(user_id=user_id, organization_id=organization_id)
    cached_at = datetime.now(UTC)
    await MailboxViewCache(view).write([], generating=True)
    return view, cached_at


def _cache_params(cached_at: datetime) -> dict:
    return {"cached_at": cached_at.isoformat(), "cached_entry_ids": "[]"}


@pytest.mark.asyncio
async def test_mailbox_sync_unsigned_subscribe_unauthorized(client: AppClient):
    """An unsigned subscribe carrying another user's user_id is rejected at subscribe time."""
    await client.get_default_user()
    other_user = await create_user(name="Other User")

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": "mailbox_sync",
                "topic_params": {"user_id": str(other_user.id)},
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED


@pytest.mark.asyncio
async def test_mailbox_view_unsigned_subscribe_unauthorized(client: AppClient):
    """An unsigned mailbox_view subscribe with another user's user_id is rejected before any view lookup."""
    await client.get_default_user()
    other_user = await create_user(name="Other User")

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": "mailbox_view",
                "topic_params": {"view_id": "template:by_goals", "user_id": str(other_user.id)},
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED


@pytest.mark.asyncio
async def test_mailbox_sync_emits_event_with_entries(client: AppClient):
    user = await client.get_default_user()
    topic = Topic("mailbox_sync", user_id=user.id)

    async with client.connect_channel(topic, params={"view": "inbox"}) as websocket:
        message = await create_email_message(
            creator_id=user.id, organization_id=user.organization_id, subject="A new thread"
        )
        await message.fetch_related("thread")
        await Mailbox.sync(message.thread)

        event = await receive_event(websocket, ChannelEventResource.MAILBOX_SYNC)
        assert event["action"] == ChannelEventAction.UPDATED
        data = event["data"]
        assert data["type"] == "entries"
        assert "entries" in data
        assert "synced_at" in data
        assert data["removed_entry_ids"] == []
        assert any(e["resource_type"] == "EmailThread" for e in data["entries"])


@pytest.mark.asyncio
async def test_mailbox_sync_skips_when_all_triggers_off_page(client: AppClient):
    """A broadcast whose entry_ids are all off-page is a no-op for the JSON handler too.

    Mirrors the HTML test added in 7d29cd50d. Without this skip, every coalesced
    off-page archive sweep during an onboarding/backfill burst still pays the
    presenter cost and pushes an event React has to diff.
    """
    user = await client.get_default_user()
    topic = Topic("mailbox_sync", user_id=user.id)

    on_page_message = await create_email_message(
        creator_id=user.id, organization_id=user.organization_id, subject="On Page Thread"
    )
    await on_page_message.fetch_related("thread")
    await Mailbox.sync(on_page_message.thread)
    on_page_entry = await MailboxEntry.first()
    assert on_page_entry is not None

    params = {
        "view": "inbox",
        "cached_entry_ids": json.dumps([str(on_page_entry.id)]),
    }

    async with client.connect_channel(topic, params=params) as websocket:
        # All trigger ids off-page → skipped silently.
        await topic.broadcast(entry_ids=[str(uuid4()), str(uuid4())])
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(websocket.receive_json(), timeout=0.5)

        # A trigger set that mixes an off-page id with the on-page entry must still
        # deliver the entries event — the coalesced-window case the skip must not drop.
        await topic.broadcast(entry_ids=[str(uuid4()), str(on_page_entry.id)])
        event = await receive_event(websocket, ChannelEventResource.MAILBOX_SYNC)
        assert event["data"]["type"] == "entries"


@pytest.mark.asyncio
async def test_mailbox_sync_emits_removed_entry_ids_for_dedupe(client: AppClient):
    """Subscriber-supplied current_entry_ids that no longer appear on page 1 are reported as removed.

    This is the cross-page dedupe contract: if the client has entry X cached on page 2 and
    a server-side change promotes page 2's head onto page 1 (so X also appears in `entries`),
    the client uses removed_entry_ids to drop the page-2 copy. Stale ids the client supplied
    that aren't in the new page 1 also appear here so the client can drop them locally.
    """
    user = await client.get_default_user()
    topic = Topic("mailbox_sync", user_id=user.id)
    stale_ids = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]

    async with client.connect_channel(
        topic, params={"view": "inbox", "current_entry_ids": '["{}", "{}"]'.format(*stale_ids)}
    ) as websocket:
        message = await create_email_message(
            creator_id=user.id, organization_id=user.organization_id, subject="Triggers a sync"
        )
        await message.fetch_related("thread")
        await Mailbox.sync(message.thread)

        event = await receive_event(websocket, ChannelEventResource.MAILBOX_SYNC)
        data = event["data"]
        assert data["type"] == "entries"
        assert set(data["removed_entry_ids"]) == set(stale_ids)
        # The new entry should not be in removed_entry_ids — it's in entries.
        new_entry_ids = {e["id"] for e in data["entries"]}
        assert not (new_entry_ids & set(data["removed_entry_ids"]))


@pytest.mark.asyncio
async def test_mailbox_sync_normalizes_mixed_case_current_entry_ids(client: AppClient):
    """Mixed-case UUIDs from the client are normalized before the dedupe diff.

    str(uuid) emits lowercase, so the new-page-1 set is always lowercase. Without
    normalization, an upper-case input would never match and would always appear in
    removed_entry_ids — a false positive.
    """
    user = await client.get_default_user()
    topic = Topic("mailbox_sync", user_id=user.id)
    upper_id = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
    lower_id = upper_id.lower()

    async with client.connect_channel(
        topic, params={"view": "inbox", "current_entry_ids": f'["{upper_id}"]'}
    ) as websocket:
        message = await create_email_message(
            creator_id=user.id, organization_id=user.organization_id, subject="Normalization"
        )
        await message.fetch_related("thread")
        await Mailbox.sync(message.thread)

        event = await receive_event(websocket, ChannelEventResource.MAILBOX_SYNC)
        data = event["data"]
        assert data["removed_entry_ids"] == [lower_id]


@pytest.mark.asyncio
async def test_mailbox_sync_accepts_legacy_route_name_alias(client: AppClient):
    """Channel subscribers using the legacy route-name vocabulary (mailbox_index) still work."""
    user = await client.get_default_user()
    topic = Topic("mailbox_sync", user_id=user.id)

    async with client.connect_channel(topic, params={"view": "mailbox_index"}) as websocket:
        message = await create_email_message(
            creator_id=user.id, organization_id=user.organization_id, subject="Legacy alias"
        )
        await message.fetch_related("thread")
        await Mailbox.sync(message.thread)

        event = await receive_event(websocket, ChannelEventResource.MAILBOX_SYNC)
        assert event["data"]["type"] == "entries"
        assert any(e["resource_type"] == "EmailThread" for e in event["data"]["entries"])


@pytest.mark.asyncio
async def test_mailbox_sync_view_mode_emits_new_messages_event(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()

    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    old_time = datetime.now(UTC) - timedelta(hours=1)
    await cache.write_json(view.cache_key, {"sections": [], "cached_at": old_time.isoformat()}, timedelta(hours=1))

    topic = Topic("mailbox_sync", user_id=user.id)

    async with client.connect_channel(
        topic,
        params={
            "mailbox_view_mode": "true",
            "view_id": str(view.id),
            "cached_at": old_time.isoformat(),
            "cached_entry_ids": "[]",
        },
    ) as websocket:
        message = await create_email_message(
            creator_id=user.id, organization_id=user.organization_id, subject="Banner trigger"
        )
        await message.fetch_related("thread")
        await Mailbox.sync(message.thread)

        event = await receive_event(websocket, ChannelEventResource.MAILBOX_SYNC)
        assert event["action"] == ChannelEventAction.UPDATED
        assert event["data"]["type"] == "new_messages"
        assert event["data"]["view_id"] == str(view.id)
        assert event["data"]["count"] >= 1


@pytest.mark.asyncio
async def test_mailbox_view_section_event_resolves_goal(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    goal = await create_goal(
        organization_id=user.organization_id, owner_id=user.id, creator_id=user.id, description="Q4"
    )
    view, cached_at = await _seed_cached_view(user.id, user.organization_id)
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic, params=_cache_params(cached_at)) as websocket:
        await topic.broadcast(
            section_index=0,
            section={
                "title": "Goal-related",
                "description": "Things tied to the goal",
                "mailbox_entry_ids": [],
                "goal_id": str(goal.id),
            },
        )

        event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
        assert event["action"] == ChannelEventAction.UPDATED
        assert event["data"]["type"] == "section"
        section_payload = event["data"]["section"]
        assert section_payload["title"] == "Goal-related"
        assert section_payload["goal"] is not None
        assert section_payload["goal"]["id"] == str(goal.id)
        assert section_payload["goal"]["description"] == "Q4"


@pytest.mark.asyncio
async def test_mailbox_view_section_events_preserve_distinct_indices(client: AppClient, use_postgres_cache):
    """Multiple section broadcasts must arrive at the client with their distinct section_index.

    React keys each rendered section by index — if the wire collapses every broadcast to
    section_index=0, every section overwrites slot 0 visually rather than being additive.
    """
    user = await client.get_default_user()
    view, cached_at = await _seed_cached_view(user.id, user.organization_id)
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic, params=_cache_params(cached_at)) as websocket:
        for i, title in enumerate(["First", "Second", "Third"]):
            await topic.broadcast(
                section_index=i,
                section={"title": title, "description": "", "mailbox_entry_ids": [], "goal_id": None},
            )

        received_indices = []
        for _ in range(3):
            event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
            assert event["data"]["type"] == "section"
            received_indices.append(event["data"]["section_index"])

        assert received_indices == [0, 1, 2], (
            f"Expected distinct section_index values 0/1/2 on the wire, got {received_indices}"
        )


@pytest.mark.asyncio
async def test_mailbox_view_complete_event_is_signal_only(client: AppClient, use_postgres_cache):
    """`complete` is a signal-only event on the React channel.

    React already has the streamed sections in state from the `section` events; re-sending
    them on `complete` caused a final full-array overwrite that collapsed any progressive
    renders into a "big bang" at the end of generation. Late joiners are covered by the
    replay path on `start_generation` (see test_mailbox_view_replays_sections_to_late_joiner).
    """
    user = await client.get_default_user()
    view, cached_at = await _seed_cached_view(user.id, user.organization_id)
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic, params=_cache_params(cached_at)) as websocket:
        await topic.broadcast(complete=True)

        event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
        assert event["action"] == ChannelEventAction.UPDATED
        assert event["data"]["type"] == "complete"
        assert "sections" not in event["data"]


@pytest.mark.asyncio
async def test_mailbox_view_replays_sections_to_late_joiner(client: AppClient, use_postgres_cache):
    """A subscriber that joins mid-stream receives the sections collected so far.

    Old `complete` payload carried sections so a late joiner caught up at the end.
    The new `complete` is signal-only — instead, when `start_generation` arrives we
    look up any in-flight session and replay its sections to the channel.
    """
    user = await client.get_default_user()
    view, cached_at = await _seed_cached_view(user.id, user.organization_id)
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    session = ViewGenerationSession(view_id=str(view.id), topic=topic)
    session.sections = [
        ViewSection(title="First", description="", mailbox_entry_ids=[str(uuid4())], goal_id=None),
        ViewSection(title="Second", description="", mailbox_entry_ids=[str(uuid4())], goal_id=None),
    ]
    # Mark the session as in-flight so the subsequent _handle_start_generation no-ops.
    session._generation_task = asyncio.create_task(asyncio.sleep(60))
    async with view_generation_manager._lock:
        view_generation_manager._sessions[str(view.id)] = session

    try:
        async with client.connect_channel(topic, params=_cache_params(cached_at)) as websocket:
            await topic.broadcast(action="start_generation")

            received: list[tuple[int, str]] = []
            for _ in range(2):
                event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
                assert event["data"]["type"] == "section"
                received.append((event["data"]["section_index"], event["data"]["section"]["title"]))

            assert received == [(0, "First"), (1, "Second")]
    finally:
        session._generation_task.cancel()
        await view_generation_manager.cleanup_session(str(view.id))


@pytest.mark.asyncio
async def test_mailbox_view_error_event(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    view, cached_at = await _seed_cached_view(user.id, user.organization_id)
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic, params=_cache_params(cached_at)) as websocket:
        await topic.broadcast(error="Something went wrong")
        event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
        assert event["action"] == ChannelEventAction.UPDATED
        assert event["data"]["type"] == "error"
        assert event["data"]["message"] == "Something went wrong"


@pytest.mark.asyncio
async def test_mailbox_view_cache_expired_event(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    view, cached_at = await _seed_cached_view(user.id, user.organization_id)
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic, params=_cache_params(cached_at)) as websocket:
        await topic.broadcast(cache_expired=True)
        event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
        assert event["action"] == ChannelEventAction.UPDATED
        assert event["data"]["type"] == "cache_expired"


@pytest.mark.asyncio
async def test_mailbox_view_new_messages_event(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    view, cached_at = await _seed_cached_view(user.id, user.organization_id)
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic, params=_cache_params(cached_at)) as websocket:
        await topic.broadcast(new_messages_count=3, view_id=str(view.id))
        event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
        assert event["action"] == ChannelEventAction.UPDATED
        assert event["data"]["type"] == "new_messages"
        assert event["data"]["count"] == 3
        assert event["data"]["view_id"] == str(view.id)


@pytest.mark.asyncio
async def test_mailbox_view_tagged_kind_dispatches_via_discriminator(client: AppClient, use_postgres_cache):
    """Producers tagged with `kind` route through the Pydantic discriminated union."""
    user = await client.get_default_user()
    view, cached_at = await _seed_cached_view(user.id, user.organization_id)
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic, params=_cache_params(cached_at)) as websocket:
        await topic.broadcast(kind="cache_expired", cache_expired=True)
        event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
        assert event["data"]["type"] == "cache_expired"

        await topic.broadcast(kind="new_messages", new_messages_count=2, view_id=str(view.id))
        event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
        assert event["data"]["type"] == "new_messages"
        assert event["data"]["count"] == 2

        # The ranked deltas must carry their recency ordinal through the discriminator + re-emit; a
        # missing field on the broadcast model would silently strip it here, reintroducing the
        # equal-score reshuffle on the client.
        await topic.broadcast(kind="entry_scored", entry_id="entry-1", score=0.5, rank=3)
        event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
        assert event["data"]["type"] == "entry_scored"
        assert event["data"]["rank"] == 3

        await topic.broadcast(kind="entries_scored", entry_ids=["entry-2", "entry-3"], ranks=[4, 5], score=-1.0)
        event = await receive_event(websocket, ChannelEventResource.MAILBOX_VIEW)
        assert event["data"]["type"] == "entries_scored"
        assert event["data"]["ranks"] == [4, 5]
