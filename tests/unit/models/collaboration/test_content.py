import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.accounts import Organization
from app.models.collaboration.content import (
    CONTENT_CITATION_PATTERN,
    INDEX_CONTENT_MAX_LENGTH,
    RESEARCH_TOKEN_PATTERN,
    CitationTokenMap,
    Content,
    ContentIndexer,
    scan_content_citations,
)
from config.enums import ContentCategory, ContentType, Sharing

# Dummy organization for testing deduplication logic
DUMMY_ORG = Organization(
    id=uuid4(),
    name="Test Org",
    created_at=datetime.now(UTC),
    updated_at=datetime.now(UTC),
)


def test_deduplicate_replaces_lower_priority():
    """When duplicate lookup_keys exist, higher priority wins"""
    # Create mock Content objects with same lookup_key but different priorities
    content1 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="doc1",
        source_url="https://example.com/1",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Meeting Notes",
        title_normalized="meeting notes",
        lookup_key="meeting:123",
        lookup_priority=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    content2 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="doc2",
        source_url="https://example.com/2",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Meeting Notes",
        title_normalized="meeting notes",
        lookup_key="meeting:123",
        lookup_priority=3,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    results = Content.deduplicate_by_lookup_key([content1, content2])

    assert len(results) == 1
    assert results[0].id == content2.id
    assert results[0].lookup_priority == 3


def test_deduplicate_preserves_order():
    """Deduplicated results maintain original order of first occurrence"""
    content_a = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="a1",
        source_url="https://example.com/a",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Document A",
        title_normalized="document a",
        lookup_key="doc:a",
        lookup_priority=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    content_b = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="b1",
        source_url="https://example.com/b",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Document B",
        title_normalized="document b",
        lookup_key="doc:b",
        lookup_priority=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    content_a2 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="a2",
        source_url="https://example.com/a2",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Document A Updated",
        title_normalized="document a updated",
        lookup_key="doc:a",
        lookup_priority=2,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    results = Content.deduplicate_by_lookup_key([content_a, content_b, content_a2])

    assert len(results) == 2
    assert results[0].lookup_key == "doc:a"
    assert results[0].id == content_a2.id
    assert results[0].lookup_priority == 2
    assert results[1].lookup_key == "doc:b"
    assert results[1].id == content_b.id


def test_deduplicate_handles_none_lookup_keys():
    """Content with lookup_key=None is not deduplicated"""

    content1 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="doc1",
        source_url="https://example.com/1",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Document 1",
        title_normalized="document 1",
        lookup_key=None,
        lookup_priority=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    content2 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="doc2",
        source_url="https://example.com/2",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Document 2",
        title_normalized="document 2",
        lookup_key=None,
        lookup_priority=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    results = Content.deduplicate_by_lookup_key([content1, content2])

    assert len(results) == 2
    assert results[0].id == content1.id
    assert results[1].id == content2.id


def test_deduplicate_complex_priorities():
    """Multiple duplicates with varying priorities"""

    content_x1 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="x1",
        source_url="https://example.com/x1",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="X Document",
        title_normalized="x document",
        lookup_key="doc:x",
        lookup_priority=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    content_y = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="y1",
        source_url="https://example.com/y",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Y Document",
        title_normalized="y document",
        lookup_key="doc:y",
        lookup_priority=5,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    content_x2 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="x2",
        source_url="https://example.com/x2",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="X Document v2",
        title_normalized="x document v2",
        lookup_key="doc:x",
        lookup_priority=2,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    content_z = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="z1",
        source_url="https://example.com/z",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Z Document",
        title_normalized="z document",
        lookup_key="doc:z",
        lookup_priority=3,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    content_x3 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="x3",
        source_url="https://example.com/x3",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="X Document v3",
        title_normalized="x document v3",
        lookup_key="doc:x",
        lookup_priority=4,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    results = Content.deduplicate_by_lookup_key([content_x1, content_y, content_x2, content_z, content_x3])

    assert len(results) == 3
    assert results[0].lookup_key == "doc:x"
    assert results[0].id == content_x3.id
    assert results[0].lookup_priority == 4
    assert results[1].lookup_key == "doc:y"
    assert results[1].id == content_y.id
    assert results[2].lookup_key == "doc:z"
    assert results[2].id == content_z.id


def test_deduplicate_keeps_first_when_equal_priority():
    """When priorities are equal, keep the first occurrence"""

    content1 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="doc1",
        source_url="https://example.com/1",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Document",
        title_normalized="document",
        lookup_key="doc:same",
        lookup_priority=2,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    content2 = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="doc2",
        source_url="https://example.com/2",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Document",
        title_normalized="document",
        lookup_key="doc:same",
        lookup_priority=2,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    results = Content.deduplicate_by_lookup_key([content1, content2])

    assert len(results) == 1
    assert results[0].id == content1.id


def test_truncate_index_content():
    dummy_content = Content(
        id=uuid4(),
        organization_id=DUMMY_ORG.id,
        category=ContentCategory.DOCUMENT,
        source_id="doc1",
        source_url="https://example.com/1",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
        title="Test",
        title_normalized="test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    indexer = ContentIndexer(content=dummy_content)

    # Text shorter than limit is returned unchanged
    short_text = "hello world"
    assert indexer._truncate_index_content(short_text) == short_text

    # Text exactly at limit is returned unchanged
    exact_text = "x" * INDEX_CONTENT_MAX_LENGTH
    result = indexer._truncate_index_content(exact_text)
    assert result == exact_text
    assert len(result) == INDEX_CONTENT_MAX_LENGTH

    # Text longer than limit is truncated to exactly INDEX_CONTENT_MAX_LENGTH
    long_text = "a" * (INDEX_CONTENT_MAX_LENGTH + 1000)
    result = indexer._truncate_index_content(long_text)
    assert len(result) == INDEX_CONTENT_MAX_LENGTH


def test_scan_content_citations():
    known = UUID("11111111-1111-1111-1111-111111111111")
    fabricated_one = UUID("22222222-2222-2222-2222-222222222222")
    fabricated_two = UUID("33333333-3333-3333-3333-333333333333")

    # Known cited twice, then both fabricated ids, then the first fabricated id repeated.
    text = (
        f"Known [^content:{known}] and again [^content:{known}]. "
        f"Fabricated [^content:{fabricated_one}] and [^content:{fabricated_two}]. "
        f"Repeat [^content:{fabricated_one}]."
    )
    known_ids = {known}

    # Only the fabricated ids come back (de-duplicated, first-appearance order); total counts every
    # marker (2 known + 2 fabricated + 1 repeat).
    assert scan_content_citations(text, known_ids) == ([fabricated_one, fabricated_two], 5)

    # Every citation resolves → nothing unresolved, but the total still counts them.
    all_known = f"[^content:{known}] and [^content:{known}]"
    assert scan_content_citations(all_known, known_ids) == ([], 2)

    # Empty / missing input → no unresolved ids and a zero total.
    assert scan_content_citations("", known_ids) == ([], 0)
    assert scan_content_citations(None, known_ids) == ([], 0)


def test_citation_token_map_for_sources_dedup_and_ordering():
    a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    c = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    token_map = CitationTokenMap.for_sources([a, b, a, c, b])

    assert token_map.token_for(a) == "S1"
    assert token_map.token_for(b) == "S2"
    assert token_map.token_for(c) == "S3"


def test_citation_token_map_round_trip():
    a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    token_map = CitationTokenMap.for_sources([a, b])

    original = f"Intro [^content:{a}], more [^content:{b}], and back to [^content:{a}] again."
    tokenized = token_map.tokenize_uuid_markers(original)
    assert tokenized == "Intro [^S1], more [^S2], and back to [^S1] again."

    assert token_map.detokenize(tokenized) == (original, [])


def test_citation_token_map_tokenize_leaves_unknown_markers():
    in_map = UUID("11111111-1111-1111-1111-111111111111")
    out_of_map = UUID("22222222-2222-2222-2222-222222222222")
    token_map = CitationTokenMap.for_sources([in_map])

    text = f"Known [^content:{in_map}] and unknown [^content:{out_of_map}]."
    result = token_map.tokenize_uuid_markers(text)

    assert result == f"Known [^S1] and unknown [^content:{out_of_map}]."


def test_citation_token_map_detokenize_drops_unknown_tokens():
    first = UUID("11111111-1111-1111-1111-111111111111")
    second = UUID("22222222-2222-2222-2222-222222222222")
    third = UUID("33333333-3333-3333-3333-333333333333")
    token_map = CitationTokenMap.for_sources([first, second, third])

    text = "valid [^S1] [^S2] [^S3], out of range [^S9], again [^S8], done."
    rewritten, unknown = token_map.detokenize(text)

    assert rewritten == (
        f"valid [^content:{first}] [^content:{second}] [^content:{third}], out of range , again , done."
    )
    assert unknown == ["S9", "S8"]


def test_research_token_and_content_citation_patterns_are_disjoint():
    content_citation = "[^content:11111111-1111-1111-1111-111111111111]"
    s_token = "[^S1]"

    assert re.search(RESEARCH_TOKEN_PATTERN, content_citation) is None
    assert re.search(CONTENT_CITATION_PATTERN, s_token) is None
