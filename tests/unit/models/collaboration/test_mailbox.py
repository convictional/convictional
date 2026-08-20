from datetime import UTC, datetime
from uuid import UUID

from app.models.collaboration.mailbox import MailboxViewCacheData, MailboxViewIdentifier
from config.enums import MailboxViewLayout

GOAL_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_ID = UUID("22222222-2222-4222-8222-222222222222")


def _ident(name: str, goal_id: UUID | None = None) -> MailboxViewIdentifier:
    # for_template returns None only for unknown template names; these tests always pass known ones.
    identifier = MailboxViewIdentifier.for_template(name, goal_id=goal_id)
    assert identifier is not None
    return identifier


def test_mailbox_view_cache_data_entry_ids():
    """Test MailboxViewCacheData extracts entry IDs from sections."""
    sections = [
        {"title": "Important", "mailbox_entry_ids": ["uuid1", "uuid2"]},
        {"title": "Later", "mailbox_entry_ids": ["uuid3"]},
    ]
    cache_data = MailboxViewCacheData(sections=sections, cached_at=datetime.now(UTC))

    assert cache_data.entry_ids == ["uuid1", "uuid2", "uuid3"]

    # Empty sections
    cache_data = MailboxViewCacheData(sections=[], cached_at=datetime.now(UTC))
    assert cache_data.entry_ids == []

    # Sections without mailbox_entry_ids key
    cache_data = MailboxViewCacheData(sections=[{"title": "Empty"}], cached_at=datetime.now(UTC))
    assert cache_data.entry_ids == []


def test_mailbox_view_cache_data_serialization():
    """Test MailboxViewCacheData serialization roundtrip."""
    sections = [{"title": "Test", "mailbox_entry_ids": ["uuid1"]}]
    cached_at = datetime.now(UTC)
    original = MailboxViewCacheData(sections=sections, cached_at=cached_at)

    serialized = original.to_dict()
    assert "sections" in serialized
    assert "cached_at" in serialized

    restored = MailboxViewCacheData.from_dict(serialized)
    assert restored.sections == original.sections
    assert abs((restored.cached_at - original.cached_at).total_seconds()) < 1


def test_mailbox_view_cache_data_round_trips_generating_flag():
    # The generating flag drives whether a refresh renders a partial as "still organizing"; it must
    # survive the cache round-trip, and default to False for caches written before the field existed.
    cached_at = datetime.now(UTC)
    partial = MailboxViewCacheData(sections=[], cached_at=cached_at, generating=True)
    assert MailboxViewCacheData.from_dict(partial.to_dict()).generating is True

    final = MailboxViewCacheData(sections=[], cached_at=cached_at)
    assert final.generating is False
    assert MailboxViewCacheData.from_dict(final.to_dict()).generating is False

    # Legacy payload without the field reads as not-generating (a completed cache).
    assert MailboxViewCacheData.from_dict({"sections": [], "cached_at": cached_at.isoformat()}).generating is False


def test_identifier_wire_string_round_trips():
    # The opaque wire string is the contract for the channel id and the per-user cache key, so
    # from_string / to_channel_id must be exact inverses for every shape we emit.
    by_goal = _ident("by_goal", goal_id=GOAL_ID)
    assert by_goal.to_channel_id() == f"template:by_goal:{GOAL_ID}"
    assert MailboxViewIdentifier.from_string(by_goal.to_channel_id()) == by_goal

    plain = _ident("priority")
    assert plain.to_channel_id() == "template:priority"
    assert MailboxViewIdentifier.from_string("template:priority") == plain

    view_id = UUID("33333333-3333-4333-8333-333333333333")
    assert MailboxViewIdentifier.from_string(str(view_id)) == MailboxViewIdentifier.for_view(view_id)


def test_identifier_rejects_malformed_wire_strings():
    # An unknown template, a malformed goal UUID, and a non-uuid bare value are all unresolvable —
    # they must return None rather than a half-built identifier that later 500s or misroutes.
    assert MailboxViewIdentifier.from_string("template:does_not_exist") is None
    assert MailboxViewIdentifier.from_string("template:by_goal:not-a-uuid") is None
    assert MailboxViewIdentifier.from_string("template:by_goal:abc:def") is None
    assert MailboxViewIdentifier.from_string("garbage") is None


def test_identifier_drops_goal_id_for_non_goal_templates():
    # Only by_goal targets a single goal. A goal_id smuggled onto any other template (via a crafted
    # wire string or a stray query param) must be dropped so it can't fragment that template's
    # channel + cache with a meaningless parameter.
    assert _ident("priority", goal_id=GOAL_ID).goal_id is None
    from_wire = MailboxViewIdentifier.from_string(f"template:priority:{GOAL_ID}")
    assert from_wire is not None and from_wire.goal_id is None
    # by_goal keeps it.
    assert _ident("by_goal", goal_id=GOAL_ID).goal_id == GOAL_ID


def test_identifier_targets_single_goal_and_layout():
    # targets_single_goal gates goal validation + goal_id round-tripping; layout drives the
    # grouped-vs-ranked fork. Both are derived from template metadata, not the literal name.
    assert _ident("by_goal").targets_single_goal is True
    assert _ident("priority").targets_single_goal is False  # ranked, no goal
    assert _ident("by_goals").targets_single_goal is False  # grouped, all goals

    assert _ident("priority").layout is MailboxViewLayout.RANKED
    assert _ident("by_goal").layout is MailboxViewLayout.RANKED
    assert _ident("by_goals").layout is MailboxViewLayout.GROUPED


def test_identifier_cache_key_includes_goal_only_for_goal_sorts():
    # The cache key is per user + template, plus goal_id only when the sort targets one — so two
    # goals never share a cache entry, but a plain template isn't keyed by an irrelevant goal.
    assert _ident("by_goal", goal_id=GOAL_ID).cache_key_for_user(USER_ID) == (
        f"mailbox_view_template_{USER_ID}_by_goal_{GOAL_ID}"
    )
    assert _ident("priority").cache_key_for_user(USER_ID) == f"mailbox_view_template_{USER_ID}_priority"
