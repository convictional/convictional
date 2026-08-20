import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from freezegun import freeze_time

from app.channels.mailbox_views import mailbox_view_subscribe
from app.models.collaboration.mailbox import MailboxViewCache
from app.presenters.mailbox_entries import MailboxEntryPresenter
from app.presenters.mailbox_view import (
    LLMMailboxRankResponse,
    LLMMailboxViewResponse,
    LLMRankedEntry,
    LLMViewSection,
    ViewSection,
)
from app.prompts import build_prompt
from app.routers.api.mailbox_views import (
    EMPTY_GENERATION_ERROR,
    SENTINEL_RANK_SCORE,
    ViewGenerationSession,
    _handle_start_generation,
    _resolve_by_goal,
)
from app.routers.dependencies import Channel
from config.enums import ChannelEventAction, ChannelEventResource, MailboxViewLayout
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_goal, create_mailbox_entry, create_mailbox_view, create_user

pytestmark = pytest.mark.real_embeddings

# Hardcoded UUIDs keep the LLM input (and therefore the cassette) stable across replays.
FIXED_ENTRY_IDS = [
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
    "55555555-5555-4555-8555-555555555555",
]


@pytest.mark.asyncio
@freeze_time("2026-05-20T12:00:00Z")
async def test_prompt_item_numbers_align_with_entry_resolution(client: AppClient):
    # The entire index→id scheme is only correct if the prompt's "Item N" ordering matches the
    # `enumerate(mailbox_entries, start=1)` map the session builds from the same list. Render the
    # real template and assert every "Item N" block names the Nth entry, and that the number→id map
    # agrees. Guards against a future reorder/filter creeping into the jinja template, which would
    # silently misfile items under the wrong section with no other test catching it.
    user = await client.get_default_user()
    now = datetime.now(UTC)
    entries = [
        await create_mailbox_entry(
            title=f"Distinct Subject {i + 1}",
            preview=f"Preview {i + 1}.",
            owner_id=user.id,
            organization_id=user.organization_id,
            last_comment_author_id=user.id,
            last_activity_at=now,
        )
        for i in range(4)
    ]
    presenters = await MailboxEntryPresenter.create_from_list(entries, user.email)

    prompt = build_prompt(
        "mailbox/customize_list.md.jinja",
        mailbox_entries=presenters,
        customization_request="organize my inbox",
        current_user=user,
        organization=user.organization,
    )

    # The session builds this exact map from the same list it renders the prompt from.
    entries_by_number = {number: str(presenter.id) for number, presenter in enumerate(presenters, start=1)}

    for number, presenter in enumerate(presenters, start=1):
        heading = f"**Item {number}**"
        start = prompt.index(heading)
        next_heading = prompt.find(f"**Item {number + 1}**")
        block = prompt[start : next_heading if next_heading != -1 else len(prompt)]

        # The subject rendered under "Item N" must be the Nth entry's, and the number→id map the
        # session resolves against must point at that same entry.
        assert presenter.title in block
        assert entries_by_number[number] == str(presenter.id)


@pytest.mark.asyncio
@freeze_time("2026-05-20T12:00:00Z")
async def test_rank_list_prompt_item_numbers_align_with_entry_resolution(client: AppClient):
    # The ranked path shares the grouped path's "Item N" → id contract: the LLM scores items by the
    # integer N, and `_generate_ranked_section` maps N back via `enumerate(mailbox_entries, start=1)`.
    # That is only correct if rank_list.md.jinja numbers items in the same order. Guards against a
    # reorder/filter creeping into the ranked template, which would silently mis-score every item.
    user = await client.get_default_user()
    now = datetime.now(UTC)
    entries = [
        await create_mailbox_entry(
            title=f"Distinct Subject {i + 1}",
            preview=f"Preview {i + 1}.",
            owner_id=user.id,
            organization_id=user.organization_id,
            last_comment_author_id=user.id,
            last_activity_at=now,
        )
        for i in range(4)
    ]
    presenters = await MailboxEntryPresenter.create_from_list(entries, user.email)

    prompt = build_prompt(
        "mailbox/rank_list.md.jinja",
        mailbox_entries=presenters,
        customization_request="rank my inbox",
        goals=None,
        current_user=user,
        organization=user.organization,
    )

    entries_by_number = {number: str(presenter.id) for number, presenter in enumerate(presenters, start=1)}

    for number, presenter in enumerate(presenters, start=1):
        heading = f"**Item {number}**"
        start = prompt.index(heading)
        next_heading = prompt.find(f"**Item {number + 1}**")
        block = prompt[start : next_heading if next_heading != -1 else len(prompt)]

        assert presenter.title in block
        assert entries_by_number[number] == str(presenter.id)


@pytest.mark.asyncio
@freeze_time("2026-05-20T12:00:00Z")
async def test_mailbox_view_streaming_generation(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    now = datetime.now(UTC)
    for i, entry_id in enumerate(FIXED_ENTRY_IDS):
        await create_mailbox_entry(
            id=entry_id,
            title=f"Important Conversation {i + 1}",
            preview=f"This is the preview of conversation {i + 1}.",
            last_comment=f"Latest reply on thread {i + 1}.",
            owner_id=user.id,
            organization_id=user.organization_id,
            last_comment_author_id=user.id,
            last_activity_at=now,
            resource_gid=f"gid://convictional/EmailThread/{entry_id}",
        )

    view = await create_mailbox_view(
        user_id=user.id,
        organization_id=user.organization_id,
        view_request="Show me important emails",
    )
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic) as websocket:
        events: list[dict] = []
        try:
            while True:
                event = await asyncio.wait_for(
                    receive_event(websocket, ChannelEventResource.MAILBOX_VIEW), timeout=15.0
                )
                events.append(event)
                if event["data"].get("type") == "complete":
                    break
        except TimeoutError as e:
            received_types = [ev["data"].get("type") for ev in events]
            raise AssertionError(
                f"Timed out waiting for `complete` event. Received types so far: {received_types}"
            ) from e

    section_events = [e for e in events if e["data"]["type"] == "section"]
    assert section_events, f"Expected at least one section event, got {[e['data']['type'] for e in events]}"
    for event in section_events:
        assert event["action"] == ChannelEventAction.UPDATED
        assert isinstance(event["data"]["section_index"], int)
        section = event["data"]["section"]
        assert isinstance(section["title"], str) and section["title"]

    assert events[-1]["data"]["type"] == "complete"


@pytest.mark.asyncio
@freeze_time("2026-05-20T12:00:00Z")
async def test_mailbox_view_streaming_retries_on_invalid_response(client: AppClient, use_postgres_cache):
    # Cassette contains two Anthropic interactions for the same request: a forged
    # `{"sections": {"foo": "bar"}}` response that trips ValidationError (and is
    # unrecoverable by the dict-unwrap helper), followed by the valid recorded
    # response. The retry layer is expected to consume both and surface a
    # `regenerating` event between them. The retry backoff is zeroed in tests
    # via `MAILBOX_RETRY_WAIT_SECONDS=0` in .env.test.
    user = await client.get_default_user()
    now = datetime.now(UTC)
    for i, entry_id in enumerate(FIXED_ENTRY_IDS):
        await create_mailbox_entry(
            id=entry_id,
            title=f"Important Conversation {i + 1}",
            preview=f"This is the preview of conversation {i + 1}.",
            last_comment=f"Latest reply on thread {i + 1}.",
            owner_id=user.id,
            organization_id=user.organization_id,
            last_comment_author_id=user.id,
            last_activity_at=now,
            resource_gid=f"gid://convictional/EmailThread/{entry_id}",
        )

    view = await create_mailbox_view(
        user_id=user.id,
        organization_id=user.organization_id,
        view_request="Show me important emails",
    )
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic) as websocket:
        events: list[dict] = []
        try:
            while True:
                event = await asyncio.wait_for(
                    receive_event(websocket, ChannelEventResource.MAILBOX_VIEW), timeout=15.0
                )
                events.append(event)
                if event["data"].get("type") == "complete":
                    break
        except TimeoutError as e:
            received_types = [ev["data"].get("type") for ev in events]
            raise AssertionError(
                f"Timed out waiting for `complete` event. Received types so far: {received_types}"
            ) from e

    types = [e["data"].get("type") for e in events]
    assert "regenerating" in types, f"Expected a regenerating event after the invalid response. Got: {types}"
    regen_event = next(e for e in events if e["data"]["type"] == "regenerating")
    assert regen_event["data"]["attempt"] == 2

    section_events = [e for e in events if e["data"]["type"] == "section"]
    assert section_events, f"Expected at least one section event after retry. Got: {types}"
    for event in section_events:
        section = event["data"]["section"]
        assert isinstance(section["title"], str) and section["title"]

    assert events[-1]["data"]["type"] == "complete"
    # `streaming_partial_json_completion` has two layered defences against bad LLM
    # responses: (1) a recovery branch that re-validates the last yielded partial
    # against the strict model — catches mid-stream corruption where some sections
    # were valid before the failure, no retry needed; (2) tenacity, which fires
    # only when even that recovery can't salvage anything. This cassette models
    # case (2): the bad response is `{"sections": {"foo": "bar"}}` from the very
    # first parse, so there's no valid intermediate partial to recover from and
    # zero sections get broadcast before `regenerating` fires. Realistic LLM
    # mid-stream failures (one valid section, then garbage) hit case (1) instead
    # and never reach this code path — so this strict ordering assertion holds
    # for the cassette but isn't a contract for production.
    regen_index = types.index("regenerating")
    section_indexes = [i for i, t in enumerate(types) if t == "section"]
    assert all(i > regen_index for i in section_indexes), (
        f"Section events emitted before regenerating signal: {list(zip(types, section_indexes, strict=False))}"
    )


@pytest.mark.asyncio
async def test_mailbox_view_cache_hit_announces_complete_only(client: AppClient, use_postgres_cache):
    # A settled cache hit re-announces `complete` on subscribe so a client stranded at generating:true
    # (its own `complete` fired while it was unsubscribed mid-generation) recovers. Nothing else is
    # emitted — the sections are already cached, and no entries arrived since cached_at to bank a
    # new-messages count.
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    await MailboxViewCache(view).write([])

    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    async with client.connect_channel(topic) as websocket:
        event = await asyncio.wait_for(receive_event(websocket, ChannelEventResource.MAILBOX_VIEW), timeout=5.0)
        assert event["data"]["type"] == "complete"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(websocket.receive_json(), timeout=1.0)


async def _drive_subscribe(user, params: dict[str, str]) -> list[dict]:
    """Run the real `mailbox_view_subscribe` handler, capturing topic broadcasts.

    The handler builds its Topic internally, so we patch the class to capture broadcasts and stub the
    auth check; a namespace stands in for the Channel (the handler only reads get_param / current_user
    / accept).
    """
    captured: list[dict] = []

    async def _capture(**data):
        captured.append(data)

    fake_topic = MagicMock()
    fake_topic.broadcast = AsyncMock(side_effect=_capture)
    channel = cast(
        Channel,
        SimpleNamespace(current_user=user, get_param=lambda name: params.get(name), accept=AsyncMock()),
    )

    with (
        patch("app.channels.mailbox_views.Topic", return_value=fake_topic),
        patch("app.channels.mailbox_views.is_current_user_authorized", AsyncMock(return_value=True)),
    ):
        await mailbox_view_subscribe(channel)
    return captured


@pytest.mark.asyncio
async def test_subscribe_decides_regeneration_from_server_cache_not_client(client: AppClient, use_postgres_cache):
    # Regression for #8330: subscribe carries only view_id, never cache state. The server decides
    # regeneration from its own cache — a present cache means no regeneration (otherwise a reconnect
    # after a cache-miss generation, which sends no baseline, would silently re-rank a valid cache).
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    await MailboxViewCache(view).write([])

    captured = await _drive_subscribe(user, {"view_id": str(view.id)})

    assert not any(c.get("action") == "start_generation" for c in captured)
    assert not any(c.get("cache_expired") for c in captured)

    # Contrast: with no cache present, the same subscribe still regenerates.
    other = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    captured = await _drive_subscribe(user, {"view_id": str(other.id)})
    assert any(c.get("action") == "start_generation" for c in captured)


@pytest.mark.asyncio
async def test_subscribe_counts_new_messages_from_cache_record(use_postgres_cache):
    # The one-shot banner count comes from the cache's OWN cached_at + entry ids, never a client
    # param: an entry that arrived after the cached order counts as new; one already in the order does
    # not, even though both are more recent than cached_at.
    user = await create_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)

    cached_at = datetime.now(UTC) - timedelta(hours=1)
    already_in_order = await create_mailbox_entry(
        owner_id=user.id, organization_id=user.organization_id, last_activity_at=datetime.now(UTC)
    )
    await create_mailbox_entry(
        owner_id=user.id, organization_id=user.organization_id, last_activity_at=datetime.now(UTC)
    )
    await MailboxViewCache(view).write(
        [{"title": "", "description": "", "goal": None, "mailbox_entry_ids": [str(already_in_order.id)]}],
        cached_at=cached_at,
    )

    captured = await _drive_subscribe(user, {"view_id": str(view.id)})

    new_messages = [c for c in captured if c.get("kind") == "new_messages"]
    assert len(new_messages) == 1
    assert new_messages[0]["new_messages_count"] == 1


@pytest.mark.asyncio
async def test_subscribe_to_completed_cache_announces_complete(use_postgres_cache):
    # A client that boosted-navigated away mid-generation and back holds generating=true: its own
    # `complete` fired to no one while unsubscribed, and the index query never re-validates. The
    # settled result is cached, so (re)subscribe must re-announce `complete` to settle the stranded
    # client.
    user = await create_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    await MailboxViewCache(view).write([])  # generating defaults to False → a settled cache

    captured = await _drive_subscribe(user, {"view_id": str(view.id)})

    assert any(c.get("complete") is True for c in captured)


@pytest.mark.asyncio
async def test_subscribe_to_generating_cache_does_not_announce_complete(use_postgres_cache):
    # An in-progress partial (generating=True) is deliberately not settled: its live session is still
    # streaming to the topic, so a spurious `complete` would freeze the client on an incomplete order.
    user = await create_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    already_in_order = await create_mailbox_entry(
        owner_id=user.id, organization_id=user.organization_id, last_activity_at=datetime.now(UTC)
    )
    await MailboxViewCache(view).write(
        [{"title": "", "description": "", "goal": None, "mailbox_entry_ids": [str(already_in_order.id)]}],
        generating=True,
    )

    captured = await _drive_subscribe(user, {"view_id": str(view.id)})

    assert not any(c.get("complete") for c in captured)


@pytest.mark.asyncio
async def test_view_generation_session_broadcasts_regenerating_on_retry(client: AppClient):
    user = await client.get_default_user()

    # Use a real Topic instance whose broadcast we spy on.
    topic = Topic("mailbox_view", view_id="test-view", user_id=str(user.id))
    broadcasts: list[dict] = []

    async def _capture_broadcast(**data):
        broadcasts.append(data)

    sections_snapshots: list[list[ViewSection]] = []

    async def fake_streaming(*, on_retry, **_kwargs):
        # First batch: emit two partials, then trigger a retry through on_retry. The LLM references
        # items by their 1-based position; the session maps those numbers to real ids.
        first_response = LLMMailboxViewResponse(
            sections=[LLMViewSection(title="A", description="", entry_numbers=[1])]
        )
        yield first_response
        sections_snapshots.append(list(session.sections))

        await on_retry(2)

        # Second batch (post-retry): emit different sections that succeed.
        second_response = LLMMailboxViewResponse(
            sections=[LLMViewSection(title="B", description="", entry_numbers=[2])]
        )
        yield second_response
        sections_snapshots.append(list(session.sections))

    session = ViewGenerationSession(view_id="test-view", topic=topic)

    cache_writer = AsyncMock()

    fake_llm = MagicMock()
    fake_llm.streaming_partial_json_completion = fake_streaming

    # Two candidate items so entry_numbers 1 and 2 resolve to real ids. Only `.id` is read when
    # building the number->id map (build_prompt is patched out), so lightweight stubs suffice.
    mailbox_entries = cast(list[MailboxEntryPresenter], [SimpleNamespace(id="entry-1"), SimpleNamespace(id="entry-2")])

    with (
        patch.object(type(user.organization), "llm", new_callable=lambda: property(lambda _self: fake_llm)),
        patch.object(topic, "broadcast", side_effect=_capture_broadcast),
        patch("app.routers.api.mailbox_views.build_prompt", return_value="system prompt"),
    ):
        await session._generate_sections_from_request(
            view_request="organize my inbox",
            mailbox_entries=mailbox_entries,
            current_user=user,
            cache_writer=cache_writer,
            cache_clearer=AsyncMock(),
        )

    kinds = [b.get("kind") for b in broadcasts]
    section_payloads = [b for b in broadcasts if "section" in b]
    regen = [b for b in broadcasts if b.get("kind") == "regenerating"]

    assert regen == [{"kind": "regenerating", "attempt": 2}]
    # Two sections emitted total — one from each batch, with the retry broadcast in between.
    assert len(section_payloads) == 2
    regen_index = kinds.index("regenerating")
    section_indexes = [i for i, b in enumerate(broadcasts) if "section" in b]
    assert section_indexes[0] < regen_index < section_indexes[1]

    # `self.sections` was cleared by the on_retry callback before the second batch arrived.
    assert sections_snapshots[0] and sections_snapshots[0][0].title == "A"
    assert sections_snapshots[1] and sections_snapshots[1][0].title == "B"
    assert all(s.title != "A" for s in sections_snapshots[1])

    assert any(b.get("complete") is True for b in broadcasts)
    # Grouped generation now writes a partial (generating=True) as each section streams so a refresh
    # mid-generation can render progress, plus a final write (generating=False) at completion. Here
    # that's section "A" (partial), section "B" post-retry (partial), then the final write.
    assert cache_writer.await_count >= 2
    assert any(call.kwargs.get("generating") for call in cache_writer.await_args_list), (
        "expected at least one partial (generating=True) cache write"
    )
    final_call = cache_writer.await_args
    assert final_call is not None
    assert final_call.kwargs.get("generating", False) is False, "final write must clear the generating flag"


@pytest.mark.asyncio
async def test_view_generation_session_errors_when_all_sections_empty(client: AppClient):
    # A non-trivial inbox that yields only unusable sections (here: item numbers outside the
    # candidate range, which resolve to zero ids and gate out) must surface an explicit error
    # instead of completing with blank sections, and must not cache the empty result.
    user = await client.get_default_user()
    topic = Topic("mailbox_view", view_id="test-view", user_id=str(user.id))
    broadcasts: list[dict] = []

    async def _capture_broadcast(**data):
        broadcasts.append(data)

    async def fake_streaming(*, on_retry, **_kwargs):
        # entry_numbers 99/100 are out of range for the two candidates below, so every section
        # resolves to no ids and is dropped by the gate.
        yield LLMMailboxViewResponse(
            sections=[
                LLMViewSection(title="Ghosts", description="", entry_numbers=[99]),
                LLMViewSection(title="More ghosts", description="", entry_numbers=[100]),
            ]
        )

    session = ViewGenerationSession(view_id="test-view", topic=topic)
    cache_writer = AsyncMock()

    fake_llm = MagicMock()
    fake_llm.streaming_partial_json_completion = fake_streaming

    mailbox_entries = cast(list[MailboxEntryPresenter], [SimpleNamespace(id="entry-1"), SimpleNamespace(id="entry-2")])

    with (
        patch.object(type(user.organization), "llm", new_callable=lambda: property(lambda _self: fake_llm)),
        patch.object(topic, "broadcast", side_effect=_capture_broadcast),
        patch("app.routers.api.mailbox_views.build_prompt", return_value="system prompt"),
    ):
        await session._generate_sections_from_request(
            view_request="organize my inbox",
            mailbox_entries=mailbox_entries,
            current_user=user,
            cache_writer=cache_writer,
            cache_clearer=AsyncMock(),
        )

    assert [b for b in broadcasts if "error" in b] == [{"error": EMPTY_GENERATION_ERROR}]
    assert not any(b.get("complete") is True for b in broadcasts)
    cache_writer.assert_not_awaited()
    assert not any("section" in b for b in broadcasts)


async def _run_ranked_generation(
    user, *, entries, ranked_response=None, partials=None, goals=None, stream_error=None, cache_clearer=None
):
    """Drive a ranked generation with a stubbed LLM response and capture broadcasts + cache writes.

    Pass `ranked_response` for a single final partial, or `partials` for a sequence of growing
    partials to exercise the mid-stream finality logic. Pass `stream_error` to raise after the
    partials (simulating a mid-stream failure), and `cache_clearer` to observe failure-path cleanup.
    """
    topic = Topic("mailbox_view", view_id="ranked-view", user_id=str(user.id))
    broadcasts: list[dict] = []
    build_prompt_calls: list[dict] = []

    async def _capture_broadcast(**data):
        broadcasts.append(data)

    stream = partials if partials is not None else [ranked_response]

    async def fake_streaming(*, on_retry, **_kwargs):
        for partial in stream:
            yield partial
        if stream_error is not None:
            raise stream_error

    def _capture_build_prompt(template, **kwargs):
        build_prompt_calls.append({"template": template, **kwargs})
        return "system prompt"

    session = ViewGenerationSession(view_id="ranked-view", topic=topic)
    cache_writer = AsyncMock()

    fake_llm = MagicMock()
    fake_llm.streaming_partial_json_completion = fake_streaming

    mailbox_entries = cast(list[MailboxEntryPresenter], [SimpleNamespace(id=eid) for eid in entries])

    with (
        patch.object(type(user.organization), "llm", new_callable=lambda: property(lambda _self: fake_llm)),
        patch.object(topic, "broadcast", side_effect=_capture_broadcast),
        patch("app.routers.api.mailbox_views.build_prompt", side_effect=_capture_build_prompt),
    ):
        await session._generate_sections_from_request(
            view_request="rank my inbox",
            mailbox_entries=mailbox_entries,
            current_user=user,
            cache_writer=cache_writer,
            cache_clearer=cache_clearer or AsyncMock(),
            goals=goals,
            layout=MailboxViewLayout.RANKED,
        )

    return broadcasts, cache_writer, build_prompt_calls, session


@pytest.mark.asyncio
async def test_ranked_generation_orders_by_score_with_sentinel_completeness(client: AppClient):
    # Five candidates in recency order entry-1..entry-5 (entry-1 most recent). The LLM scores four
    # of them; entry-4 is left unscored. The server sorts by score desc, tie-broken by recency
    # (candidate index) then id, and assigns the unscored candidate a sentinel bottom score so the
    # ranked section remains a COMPLETE set of all five candidates rather than silently dropping one.
    user = await client.get_default_user()
    entries = ["entry-1", "entry-2", "entry-3", "entry-4", "entry-5"]
    ranked_response = LLMMailboxRankResponse(
        entries=[
            LLMRankedEntry(entry_number=1, score=0.2),
            LLMRankedEntry(entry_number=2, score=0.9),
            LLMRankedEntry(entry_number=3, score=0.5),
            LLMRankedEntry(entry_number=5, score=0.9),
        ]
    )

    broadcasts, cache_writer, _calls, _session = await _run_ranked_generation(
        user, entries=entries, ranked_response=ranked_response
    )

    # Streaming transport is per-entry deltas, not whole-section frames: one `entry_scored` per
    # LLM-scored candidate, each exactly once.
    deltas = [b for b in broadcasts if b.get("kind") == "entry_scored"]
    scores_by_id = {d["entry_id"]: d["score"] for d in deltas}
    assert len(deltas) == len(scores_by_id) == 4  # one delta per scored candidate, no dupes
    assert scores_by_id == {"entry-1": 0.2, "entry-2": 0.9, "entry-3": 0.5, "entry-5": 0.9}
    # Each delta carries the candidate's recency ordinal (its index in the candidate list) so the
    # client tie-breaks equal scores exactly as order_candidates does, with no reshuffle on hydration.
    ranks_by_id = {d["entry_id"]: d["rank"] for d in deltas}
    assert ranks_by_id == {"entry-1": 0, "entry-2": 1, "entry-3": 2, "entry-5": 4}
    # The unscored candidate ships in a single batched sentinel frame, not one NOTIFY each, with a
    # parallel ranks array aligned to entry_ids.
    sentinel_frames = [b for b in broadcasts if b.get("kind") == "entries_scored"]
    assert len(sentinel_frames) == 1
    assert sentinel_frames[0]["entry_ids"] == ["entry-4"]
    assert sentinel_frames[0]["ranks"] == [3]
    assert sentinel_frames[0]["score"] == SENTINEL_RANK_SCORE
    # No whole-section frame is broadcast during ranked streaming anymore.
    assert not any("section" in b for b in broadcasts)
    assert any(b.get("complete") is True for b in broadcasts)

    # The server still accumulates + caches the whole score-sorted section (titleless, complete set)
    # for the next page load and late-subscriber replay. 0.9 ties: entry-2 (recency rank 1) before
    # entry-5 (rank 4); then 0.5, 0.2, sentinel last.
    cache_writer.assert_awaited_once()
    cached = cache_writer.await_args.args[0]
    assert cached[0]["mailbox_entry_ids"] == ["entry-2", "entry-5", "entry-3", "entry-1", "entry-4"]
    assert cached[0]["title"] == ""


@pytest.mark.asyncio
async def test_ranked_generation_writes_partial_orderings_while_streaming(client: AppClient):
    # A refresh mid-sort must render the best-available order instead of blanking, so ranked
    # generation throttle-writes a partial ordering (generating=True) once enough new scores have
    # landed, then a final write (generating=False) at completion. With 12 candidates streamed
    # across two partials, the first partial crosses the 10-score threshold and triggers a partial
    # write; the final write clears the flag and holds the complete set.
    user = await client.get_default_user()
    entries = [f"entry-{i}" for i in range(1, 13)]
    # Partial A scores items 1..11 (the inner loop ingests 1..10, deferring the trailing one),
    # crossing the threshold. Partial B adds item 12 so the set is complete.
    partial_a = LLMMailboxRankResponse(
        entries=[LLMRankedEntry(entry_number=n, score=1.0 - n / 100) for n in range(1, 12)]
    )
    partial_b = LLMMailboxRankResponse(
        entries=[LLMRankedEntry(entry_number=n, score=1.0 - n / 100) for n in range(1, 13)]
    )

    _broadcasts, cache_writer, _calls, _session = await _run_ranked_generation(
        user, entries=entries, partials=[partial_a, partial_b]
    )

    # At least one partial (generating=True) write before the final write.
    partial_writes = [c for c in cache_writer.await_args_list if c.kwargs.get("generating")]
    assert partial_writes, "expected a partial (generating=True) cache write mid-stream"
    # Partials carry a stable cached_at so the new-messages baseline doesn't drift across writes.
    assert all("cached_at" in c.kwargs and c.kwargs["cached_at"] is not None for c in partial_writes)
    # Final write clears the flag and holds every candidate.
    final_call = cache_writer.await_args
    assert final_call is not None
    assert final_call.kwargs.get("generating", False) is False
    assert set(final_call.args[0][0]["mailbox_entry_ids"]) == set(entries)


@pytest.mark.asyncio
async def test_ranked_generation_clears_partial_cache_when_stream_fails(client: AppClient):
    # If generation fails AFTER a partial (generating=True) write, the stale partial must be deleted
    # so the next load is a clean cache-miss that regenerates — not a stuck partial the cache-hit
    # subscribe path would never refresh.
    user = await client.get_default_user()
    entries = [f"entry-{i}" for i in range(1, 13)]
    # Scores 1..11 → the inner loop ingests 1..10, crossing the partial-write threshold; then the
    # stream raises before completion.
    partial = LLMMailboxRankResponse(
        entries=[LLMRankedEntry(entry_number=n, score=1.0 - n / 100) for n in range(1, 12)]
    )
    cache_clearer = AsyncMock()

    broadcasts, cache_writer, _calls, _session = await _run_ranked_generation(
        user,
        entries=entries,
        partials=[partial],
        stream_error=RuntimeError("stream blew up"),
        cache_clearer=cache_clearer,
    )

    # A partial was written, the generation errored (no `complete`), and the partial was cleared.
    assert any(c.kwargs.get("generating") for c in cache_writer.await_args_list)
    assert not any(b.get("complete") is True for b in broadcasts)
    assert any("error" in b for b in broadcasts)
    cache_clearer.assert_awaited_once()


@pytest.mark.asyncio
async def test_ranked_generation_errors_when_nothing_scored(client: AppClient):
    # The LLM scores nothing usable (all entry numbers out of range). Unlike grouped, a ranked
    # section would otherwise always be non-empty (sentinels fill it), so the empty guard must key
    # off "the LLM scored at least one real candidate", surface an explicit error, and not cache.
    user = await client.get_default_user()
    ranked_response = LLMMailboxRankResponse(
        entries=[LLMRankedEntry(entry_number=98, score=0.9), LLMRankedEntry(entry_number=99, score=0.1)]
    )

    broadcasts, cache_writer, _calls, _session = await _run_ranked_generation(
        user, entries=["entry-1", "entry-2"], ranked_response=ranked_response
    )

    assert [b for b in broadcasts if "error" in b] == [{"error": EMPTY_GENERATION_ERROR}]
    assert not any(b.get("complete") is True for b in broadcasts)
    cache_writer.assert_not_awaited()
    # Nothing scored → no deltas (not even sentinels) and no section frame.
    assert not any(b.get("kind") == "entry_scored" for b in broadcasts)
    assert not any(b.get("kind") == "entries_scored" for b in broadcasts)
    assert not any("section" in b for b in broadcasts)


@pytest.mark.asyncio
async def test_ranked_generation_injects_goal_and_uses_rank_prompt(client: AppClient):
    # A goal-targeted ranked sort must win before the grouped goals fork: it uses the rank_list
    # prompt (not organize_by_goals) and passes the single chosen goal through to it.
    user = await client.get_default_user()
    goal = SimpleNamespace(id="goal-1", description="Ship V1")
    ranked_response = LLMMailboxRankResponse(entries=[LLMRankedEntry(entry_number=1, score=0.7)])

    _broadcasts, _cache_writer, calls, _session = await _run_ranked_generation(
        user, entries=["entry-1", "entry-2"], ranked_response=ranked_response, goals=[goal]
    )

    assert len(calls) == 1
    assert calls[0]["template"] == "mailbox/rank_list.md.jinja"
    assert calls[0]["goals"] == [goal]


@pytest.mark.asyncio
async def test_ranked_generation_defers_trailing_entry_until_score_is_final(client: AppClient):
    # instructor yields growing partials; a trailing entry's score can be caught mid-parse (0 before
    # 0.8). The session emits an entry only once a LATER entry appears (so its object is final) and
    # tail-flushes the very last one. Drive three growing partials where each trailing entry's score
    # starts at a transient 0.0 and settles on its real value, and assert every entry_scored fires
    # exactly once with the FINAL score — never the mid-parse transient.
    user = await client.get_default_user()
    entries = ["entry-1", "entry-2", "entry-3"]
    partials = [
        # entry-1 trailing & mid-parse — must not be emitted yet.
        LLMMailboxRankResponse(entries=[LLMRankedEntry(entry_number=1, score=0.0)]),
        # entry-1 now final at 0.8 (a successor appeared); entry-2 trailing & mid-parse.
        LLMMailboxRankResponse(
            entries=[LLMRankedEntry(entry_number=1, score=0.8), LLMRankedEntry(entry_number=2, score=0.0)]
        ),
        # entry-2 now final at 0.5; entry-3 trailing — deferred to the tail-flush.
        LLMMailboxRankResponse(
            entries=[
                LLMRankedEntry(entry_number=1, score=0.8),
                LLMRankedEntry(entry_number=2, score=0.5),
                LLMRankedEntry(entry_number=3, score=0.3),
            ]
        ),
    ]

    broadcasts, cache_writer, _calls, _session = await _run_ranked_generation(user, entries=entries, partials=partials)

    deltas = [b for b in broadcasts if b.get("kind") == "entry_scored"]
    scores_by_id = {d["entry_id"]: d["score"] for d in deltas}
    # Each entry emitted exactly once, at its final score — the transient 0.0s are never broadcast.
    assert len(deltas) == len(scores_by_id) == 3
    assert scores_by_id == {"entry-1": 0.8, "entry-2": 0.5, "entry-3": 0.3}
    # Every candidate was scored, so there is no sentinel frame.
    assert not any(b.get("kind") == "entries_scored" for b in broadcasts)
    assert any(b.get("complete") is True for b in broadcasts)

    cache_writer.assert_awaited_once()
    cached = cache_writer.await_args.args[0]
    assert cached[0]["mailbox_entry_ids"] == ["entry-1", "entry-2", "entry-3"]


@pytest.mark.asyncio
async def test_ranked_generation_scores_raw_dict_trailing_entry(client: AppClient):
    # The partial parser only finalizes an array element into an LLMRankedEntry once a LATER element
    # proves it complete, so the final partial's trailing element (the one the tail-flush reads) can
    # still be a raw dict. Regression: `resolve` used to do attribute access and crash with
    # `AttributeError: 'dict' object has no attribute 'entry_number'`, which the broad except turned
    # into a generic error that wiped the inbox. Drive a final partial whose finalized lead element
    # is a model and whose trailing element is a raw dict, and assert both score without erroring.
    user = await client.get_default_user()
    entries = ["entry-1", "entry-2"]
    partials = [
        SimpleNamespace(entries=[LLMRankedEntry(entry_number=1, score=0.2), {"entry_number": 2, "score": 0.8}]),
    ]

    broadcasts, cache_writer, _calls, _session = await _run_ranked_generation(user, entries=entries, partials=partials)

    deltas = [b for b in broadcasts if b.get("kind") == "entry_scored"]
    scores_by_id = {d["entry_id"]: d["score"] for d in deltas}
    assert scores_by_id == {"entry-1": 0.2, "entry-2": 0.8}
    # The dict trailing entry resolved cleanly: no generic-error broadcast, generation completed.
    assert not any("error" in b for b in broadcasts)
    assert any(b.get("complete") is True for b in broadcasts)
    cache_writer.assert_awaited_once()
    assert cache_writer.await_args.args[0][0]["mailbox_entry_ids"] == ["entry-2", "entry-1"]


async def _drive_start_generation(user, view_id_str) -> list[dict]:
    """Run the real channel entry point `_handle_start_generation`, capturing topic broadcasts.

    Exercises identifier parsing, source resolution, and goal resolution — the path the per-method
    ranked tests skip. The Topic is built inside the handler, so we patch the class to capture its
    broadcasts. The error branches all return before any LLM call.
    """
    captured: list[dict] = []

    async def _capture(**data):
        captured.append(data)

    fake_topic = MagicMock()
    fake_topic.broadcast = AsyncMock(side_effect=_capture)
    # The handler only reads `channel.current_user`; a namespace stands in for the real Channel.
    channel = cast(Channel, SimpleNamespace(current_user=user))

    with patch("app.routers.api.mailbox_views.Topic", return_value=fake_topic):
        await _handle_start_generation(channel, view_id_str)
    return captured


@pytest.mark.asyncio
async def test_channel_by_goal_resolution_messages(client: AppClient):
    # The by_goal channel branch resolves the goal org-scoped (defense-in-depth) and, when it was
    # valid at request time but deleted/closed since, surfaces a message specific to a single-goal
    # sort rather than the plural "create a goal first" prompt.
    user = await create_user()

    # Closed goal → distinct "was closed" message.
    closed_goal = await create_goal(
        organization_id=user.organization_id,
        owner_id=user.id,
        creator_id=user.id,
        closed_at=datetime.now(UTC),
    )
    captured = await _drive_start_generation(user, f"template:by_goal:{closed_goal.id}")
    assert captured == [{"error": "This goal was closed. Pick another goal or sort."}]

    # Deleted/foreign goal → "no longer available".
    captured = await _drive_start_generation(user, f"template:by_goal:{uuid4()}")
    assert captured == [{"error": "This goal is no longer available."}]


@pytest.mark.asyncio
async def test_channel_by_goal_valid_goal_resolves(client: AppClient):
    # The success branch: a valid open goal resolves, so the flow proceeds past goal resolution to
    # the candidate-count check. With an empty inbox it stops there — proving the goal was resolved
    # (no goal error) without needing the LLM.
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id, owner_id=user.id, creator_id=user.id)

    captured = await _drive_start_generation(user, f"template:by_goal:{goal.id}")

    assert captured == [{"error": "There aren't enough emails to organize. Try again when your inbox fills up."}]


@pytest.mark.asyncio
async def test_by_goal_resolved_goal_renders_rank_prompt(client: AppClient):
    # Regression: the by_goal goal flows into BOTH rank_list.md.jinja and the shared org system
    # prompt, which reads `goal.subgoals` (a reverse relation). _resolve_by_goal must prefetch it, or
    # the Jinja render raises NoValuesFetched inside build_prompt — which runs outside the ranked
    # engine's try, so the generation task dies silently and the view sticks on "Organizing…".
    # The other by_goal tests stop at the empty-inbox guard before build_prompt, so they miss this.
    user = await create_user()
    parent = await create_goal(organization_id=user.organization_id, owner_id=user.id, creator_id=user.id)
    await create_goal(organization_id=user.organization_id, owner_id=user.id, creator_id=user.id, parent_id=parent.id)

    goal, rejection = await _resolve_by_goal(parent.id, user, with_relations=True)
    assert rejection is None and goal is not None

    # Accessing the prefetched reverse relation must not raise, and the prompt must render.
    assert goal.subgoals is not None
    await user.fetch_related("organization")
    prompt = build_prompt(
        "mailbox/rank_list.md.jinja",
        mailbox_entries=[],
        customization_request="",
        goals=[goal],
        current_user=user,
        organization=user.organization,
    )
    # The goals block rendered (it reads goal.subgoals) without raising NoValuesFetched.
    assert "The Goal to Prioritize For" in prompt


@pytest.mark.asyncio
@freeze_time("2026-05-20T12:00:00Z")
async def test_ranked_view_streaming_generation_e2e(client: AppClient, use_postgres_cache):
    # End-to-end ranked generation over the real channel + real LLM (recorded cassette). The
    # per-method ranked tests stub the model and call the private generator directly; this is the
    # only test that exercises _handle_start_generation → start_generation_with_request, the real
    # rank_list.md.jinja render, instructor Partial streaming of LLMMailboxRankResponse, and the
    # on-wire entry_scored / entries_scored / complete event shapes. Assertions are structural
    # (completeness + score range) so they don't pin the recorded model's exact scores.
    user = await create_user(email="ranked-e2e@convictional.com")
    now = datetime.now(UTC)
    for i, entry_id in enumerate(FIXED_ENTRY_IDS):
        await create_mailbox_entry(
            id=entry_id,
            title=f"Important Conversation {i + 1}",
            preview=f"This is the preview of conversation {i + 1}.",
            last_comment=f"Latest reply on thread {i + 1}.",
            owner_id=user.id,
            organization_id=user.organization_id,
            last_comment_author_id=user.id,
            last_activity_at=now,
            resource_gid=f"gid://convictional/EmailThread/{entry_id}",
        )

    view = await create_mailbox_view(
        user_id=user.id,
        organization_id=user.organization_id,
        view_request="Rank my inbox so the most urgent conversations come first",
        layout="ranked",
    )
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    with client.current_user_as(user):
        async with client.connect_channel(topic) as websocket:
            events: list[dict] = []
            try:
                while True:
                    event = await asyncio.wait_for(
                        receive_event(websocket, ChannelEventResource.MAILBOX_VIEW), timeout=15.0
                    )
                    events.append(event)
                    if event["data"].get("type") == "complete":
                        break
            except TimeoutError as e:
                received_types = [ev["data"].get("type") for ev in events]
                raise AssertionError(f"Timed out waiting for `complete`. Received: {received_types}") from e

    # Ranked streams per-entry score deltas (and a batched sentinel frame for any unscored), never
    # grouped section frames.
    assert not any(ev["data"]["type"] == "section" for ev in events)
    assert events[-1]["data"]["type"] == "complete"

    scored_ids = set()
    for ev in events:
        if ev["data"]["type"] == "entry_scored":
            assert 0.0 <= ev["data"]["score"] <= 1.0
            scored_ids.add(ev["data"]["entry_id"])

    sentinel_ids: set[str] = set()
    for ev in events:
        if ev["data"]["type"] == "entries_scored":
            assert ev["data"]["score"] == SENTINEL_RANK_SCORE
            sentinel_ids.update(ev["data"]["entry_ids"])

    # The LLM scored at least one real candidate, and every candidate is either scored or
    # sentinel-filled — the ranked set is complete, never silently dropping an item.
    assert scored_ids
    assert scored_ids | sentinel_ids == set(FIXED_ENTRY_IDS)


@pytest.mark.asyncio
@freeze_time("2026-05-20T12:00:00Z")
async def test_ranked_view_streaming_retries_on_invalid_response(client: AppClient, use_postgres_cache):
    # Ranked parallel to test_mailbox_view_streaming_retries_on_invalid_response. The cassette holds
    # two interactions: a forged `{"entries": {"foo": "bar"}}` response that trips an unrecoverable
    # ValidationError on LLMMailboxRankResponse (entries must be a list), then the valid recorded
    # response. The shared retry layer consumes both, and the ranked on_retry clears any
    # partially-scored state and broadcasts `regenerating` before the clean second attempt streams.
    # Backoff is zeroed via MAILBOX_RETRY_WAIT_SECONDS=0 in .env.test.
    user = await create_user(email="ranked-e2e@convictional.com")
    now = datetime.now(UTC)
    for i, entry_id in enumerate(FIXED_ENTRY_IDS):
        await create_mailbox_entry(
            id=entry_id,
            title=f"Important Conversation {i + 1}",
            preview=f"This is the preview of conversation {i + 1}.",
            last_comment=f"Latest reply on thread {i + 1}.",
            owner_id=user.id,
            organization_id=user.organization_id,
            last_comment_author_id=user.id,
            last_activity_at=now,
            resource_gid=f"gid://convictional/EmailThread/{entry_id}",
        )

    view = await create_mailbox_view(
        user_id=user.id,
        organization_id=user.organization_id,
        view_request="Rank my inbox so the most urgent conversations come first",
        layout="ranked",
    )
    topic = Topic("mailbox_view", view_id=str(view.id), user_id=str(user.id))

    with client.current_user_as(user):
        async with client.connect_channel(topic) as websocket:
            events: list[dict] = []
            try:
                while True:
                    event = await asyncio.wait_for(
                        receive_event(websocket, ChannelEventResource.MAILBOX_VIEW), timeout=15.0
                    )
                    events.append(event)
                    if event["data"].get("type") == "complete":
                        break
            except TimeoutError as e:
                received_types = [ev["data"].get("type") for ev in events]
                raise AssertionError(f"Timed out waiting for `complete`. Received: {received_types}") from e

    types = [e["data"].get("type") for e in events]
    assert "regenerating" in types, f"Expected a regenerating event after the invalid response. Got: {types}"
    regen_event = next(e for e in events if e["data"]["type"] == "regenerating")
    assert regen_event["data"]["attempt"] == 2

    # The clean second attempt scores the inbox; completeness still holds after the retry.
    scored_ids = {e["data"]["entry_id"] for e in events if e["data"]["type"] == "entry_scored"}
    sentinel_ids: set[str] = set()
    for ev in events:
        if ev["data"]["type"] == "entries_scored":
            sentinel_ids.update(ev["data"]["entry_ids"])
    assert scored_ids
    assert scored_ids | sentinel_ids == set(FIXED_ENTRY_IDS)
    assert events[-1]["data"]["type"] == "complete"

    # The forged first response yields nothing parseable, so on_retry clears state and `regenerating`
    # fires before any score delta — no scores leak from the failed attempt. (Holds for this forged
    # cassette; a real mid-stream failure with a valid prefix would recover without retrying.)
    regen_index = types.index("regenerating")
    delta_indexes = [i for i, t in enumerate(types) if t in ("entry_scored", "entries_scored")]
    assert all(i > regen_index for i in delta_indexes), f"Score deltas emitted before the regenerating signal: {types}"


@pytest.mark.asyncio
async def test_ranked_generation_skips_non_list_entries_partial(client: AppClient):
    # instructor can momentarily yield a partial whose `entries` parsed as a non-list (a malformed
    # object mid-parse). The consumer must skip it rather than crash on `entries[:-1]`, then score
    # normally from the well-formed partials that follow.
    user = await client.get_default_user()
    partials = [
        SimpleNamespace(entries={"foo": "bar"}),  # malformed mid-parse shape — must be skipped
        LLMMailboxRankResponse(entries=[LLMRankedEntry(entry_number=1, score=0.4)]),
    ]

    broadcasts, cache_writer, _calls, _session = await _run_ranked_generation(
        user, entries=["entry-1", "entry-2"], partials=partials
    )

    scores_by_id = {b["entry_id"]: b["score"] for b in broadcasts if b.get("kind") == "entry_scored"}
    assert scores_by_id == {"entry-1": 0.4}
    sentinel = [b for b in broadcasts if b.get("kind") == "entries_scored"]
    assert sentinel == [
        {"kind": "entries_scored", "entry_ids": ["entry-2"], "ranks": [1], "score": SENTINEL_RANK_SCORE}
    ]
    assert any(b.get("complete") is True for b in broadcasts)
    cache_writer.assert_awaited_once()
