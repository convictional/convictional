import pytest
from pydantic import ValidationError

from app.presenters.mailbox_view import LLMViewSection
from app.routers.api.mailbox_entries import _LOOKUP_FETCH_MAX
from app.routers.api.mailbox_views import (
    MAILBOX_VIEW_MAX_ENTRIES,
    EntriesScoredBroadcast,
    _as_llm_section,
    _coerce_entry_numbers,
    _gated_section,
    _resolve_entry_numbers,
    _view_section_from_llm,
)


def _entries_by_number(*ids: str) -> dict[int, str]:
    return {number: entry_id for number, entry_id in enumerate(ids, start=1)}


def test_resolve_entry_numbers_maps_drops_and_dedupes():
    entries_by_number = _entries_by_number("aaa", "bbb", "ccc")

    # In-range numbers map to ids in order; out-of-range (0, negative, beyond the list) are dropped;
    # repeats collapse to a single id while preserving first-seen order.
    assert _resolve_entry_numbers([2, 1], entries_by_number) == ["bbb", "aaa"]
    assert _resolve_entry_numbers([0, 4, -1, 99], entries_by_number) == []
    assert _resolve_entry_numbers([1, 1, 2, 1], entries_by_number) == ["aaa", "bbb"]
    assert _resolve_entry_numbers([], entries_by_number) == []


def test_view_section_from_llm_resolves_numbers_to_real_ids():
    entries_by_number = _entries_by_number("id-1", "id-2", "id-3")
    goal_id = "f9472e54-1111-4f1f-8f1f-f9472e541111"
    llm_section = LLMViewSection(title="Urgent", description="needs attention", entry_numbers=[3, 1], goal_id=goal_id)

    section = _view_section_from_llm(llm_section, entries_by_number)

    assert section.title == "Urgent"
    assert section.description == "needs attention"
    assert section.goal_id == goal_id
    assert section.mailbox_entry_ids == ["id-3", "id-1"]


def test_view_section_from_llm_drops_malformed_goal_id():
    # The LLM transcribes goal_id as a raw 36-char UUID and routinely truncates it. A mangled id
    # must drop to None here, or it poisons the cache and 500s every later Goal.filter(id__in=...).
    entries_by_number = _entries_by_number("id-1")
    section = _view_section_from_llm(
        LLMViewSection(title="Urgent", entry_numbers=[1], goal_id="f9472e54-1"), entries_by_number
    )

    assert section.goal_id is None
    assert section.mailbox_entry_ids == ["id-1"]


def test_as_llm_section_coerces_self_nested_dicts():
    # Passes validated instances through untouched.
    section = LLMViewSection(title="A", entry_numbers=[1])
    assert _as_llm_section(section) is section

    # When Sonnet self-nests, the unwrap repair hoists raw dicts; coerce them into the model so a
    # self-nested response still produces sections instead of a silent blank.
    coerced = _as_llm_section({"title": "B", "description": "d", "entry_numbers": [2, 3], "goal_id": None})
    assert isinstance(coerced, LLMViewSection)
    assert coerced.title == "B"
    assert coerced.entry_numbers == [2, 3]

    # Non-section values yield None so the gate skips them.
    assert _as_llm_section("not a section") is None
    assert _as_llm_section(None) is None


def test_view_section_from_llm_drops_fabricated_numbers():
    # A section whose numbers are all out of range resolves to zero ids, so the generation gate
    # (title and mailbox_entry_ids both truthy) drops it instead of caching an empty section.
    entries_by_number = _entries_by_number("id-1", "id-2")
    llm_section = LLMViewSection(title="Bogus", entry_numbers=[7, 8, 9])

    section = _view_section_from_llm(llm_section, entries_by_number)

    assert section.mailbox_entry_ids == []


def test_coerce_entry_numbers_salvages_valid_drops_malformed():
    # Ints pass; whole-valued floats and digit strings coerce; fractional floats, bools, None, and
    # non-numeric junk are dropped rather than sinking the whole section they belong to.
    assert _coerce_entry_numbers([1, 2, 3]) == [1, 2, 3]
    assert _coerce_entry_numbers([2.0, "3", " 4 "]) == [2, 3, 4]
    assert _coerce_entry_numbers([2.5, "x", None, True, [1]]) == []
    assert _coerce_entry_numbers("not a list") == []


def test_as_llm_section_salvages_section_with_one_bad_number():
    # A self-nested raw dict whose entry_numbers contains a malformed value must still yield a
    # section carrying its valid numbers. Dropping the entire section over one bad number would
    # reintroduce the silent blanking that moving off hand-transcribed UUIDs set out to fix.
    coerced = _as_llm_section({"title": "Mixed", "entry_numbers": [1, 2.5, "x", 3]})

    assert isinstance(coerced, LLMViewSection)
    assert coerced.entry_numbers == [1, 3]


def test_gated_section_coerces_resolves_and_gates():
    entries_by_number = _entries_by_number("id-1", "id-2", "id-3")

    # Valid raw section → coerced, resolved, and returned.
    section = _gated_section({"title": "Keep", "entry_numbers": [2, 1]}, entries_by_number)
    assert section is not None
    assert section.mailbox_entry_ids == ["id-2", "id-1"]

    # Title but all numbers out of range (resolves to no ids) → dropped by the gate.
    assert _gated_section({"title": "Bogus", "entry_numbers": [9]}, entries_by_number) is None
    # Resolvable ids but no title → dropped by the gate.
    assert _gated_section({"title": "", "entry_numbers": [1]}, entries_by_number) is None
    # Not a section at all → dropped.
    assert _gated_section("nope", entries_by_number) is None


def test_lookup_cap_covers_generation_limit():
    # Regression guard: a ranked view section holds every considered candidate (up to
    # MAILBOX_VIEW_MAX_ENTRIES), and the client hydrates them through /mailbox_entries/lookup in one
    # request. If the lookup cap is below the generation limit, the overflow ids never hydrate and are
    # silently filtered from the rendered list.
    assert _LOOKUP_FETCH_MAX >= MAILBOX_VIEW_MAX_ENTRIES


def test_entries_scored_broadcast_enforces_aligned_ranks():
    # Aligned arrays pass.
    broadcast = EntriesScoredBroadcast(entry_ids=["a", "b"], ranks=[0, 1], score=-1.0)
    assert broadcast.ranks == [0, 1]

    # A ranks array that doesn't line up with entry_ids would silently corrupt client ordering, so
    # the model rejects it rather than letting the mismatch through.
    with pytest.raises(ValidationError):
        EntriesScoredBroadcast(entry_ids=["a", "b"], ranks=[0], score=-1.0)
