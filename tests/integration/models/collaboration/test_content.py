import logging
from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.content import ContentIndexingJob, IndexEmailContactJob
from app.models.collaboration.content import (
    Content,
    ContentIndexer,
    ContentLookup,
    ContentLookupQuery,
    ContentResearchQuery,
    IndexingID,
    IndexMetadata,
    SearchableData,
)
from app.models.workspaces.meetings import Meeting, Transcript, TranscriptLine
from config import settings
from config.enums import ContentCategory, ContentType, Sharing
from infra.db import GlobalID
from tests.helpers.factories import create_content, create_email_contact, create_organization, create_user

# This module is dominated by search/lookup tests whose assertions depend on real
# embedding-ranked retrieval; keep recorded OpenAI vectors for the whole file.
pytestmark = pytest.mark.real_embeddings


@pytest.mark.asyncio
async def test_basic_content_search():
    organization = await create_organization()
    content = await create_content(
        title="Test Content",
        content_type=ContentType.FILE,
        source_url="https://example.com",
        organization_id=organization.id,
    )

    results = await ContentResearchQuery(organization=organization, query="Test Content").execute()
    assert len(results) == 1
    assert results[0].id == content.id

    results = await ContentResearchQuery(
        organization=organization, query="Test Content", exclude_source_urls=["https://example.com"]
    ).execute()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_searching_with_double_quotes():
    organization = await create_organization()
    first = await create_content(organization=organization)
    await first.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    second = await create_content(organization=organization)
    await second.indexer.index(
        SearchableData("Bananas", "Bananas are a yellow fruit", "https://example.com/bananas", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    third = await create_content(organization=organization)
    await third.indexer.index(
        SearchableData("Oranges", "Oranges are an orange fruit", "https://example.com/oranges", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    results = await ContentResearchQuery(organization=organization, query="fruit").execute()
    assert len(results) == 3
    assert first in results
    assert second in results
    assert third in results

    results = await ContentResearchQuery(organization=organization, query="apple").execute()
    assert len(results) == 3
    assert results[0] == first
    assert second in results
    assert third in results

    # Set result_threshold to 0 to disable fallback for this test
    results = await ContentResearchQuery(
        organization=organization, query='"red fruit"', minimum_results_with_exact_matching=0
    ).execute()
    assert len(results) == 1
    assert first in results


@pytest.mark.asyncio
async def test_searching_with_date_ranges():
    # Remove microseconds so we have neat boundaries
    now = datetime.now(UTC).replace(microsecond=0)
    organization = await create_organization()

    # All three share an old created_at; the date range must key off updated_at (last activity),
    # not created_at — a meeting indexed weeks before it happens would otherwise be unfindable in
    # the window it actually occurred in.
    created_at = now - timedelta(days=90)

    first = await create_content(organization=organization)
    await first.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST_COMMENT,
            Sharing.ORGANIZATION,
            created_at=created_at,
            updated_at=now - timedelta(days=1),
        ),
    )

    second = await create_content(organization=organization)
    await second.indexer.index(
        SearchableData("Bananas", "Bananas are a yellow fruit", "https://example.com/bananas", "Bob Clams"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST_COMMENT,
            Sharing.ORGANIZATION,
            created_at=created_at,
            updated_at=now - timedelta(days=2),
        ),
    )

    third = await create_content(organization=organization)
    await third.indexer.index(
        SearchableData("Oranges", "Oranges are an orange fruit", "https://example.com/oranges", "Bob Clams"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST_COMMENT,
            Sharing.ORGANIZATION,
            created_at=created_at,
            updated_at=now - timedelta(days=3),
        ),
    )

    results = await ContentResearchQuery(
        organization=organization, query="fruit", starts_at=now - timedelta(days=2)
    ).execute()
    assert len(results) == 2
    assert first in results
    assert second in results
    assert third not in results

    results = await ContentResearchQuery(
        organization=organization, query="fruit", ends_at=now - timedelta(days=2)
    ).execute()
    assert len(results) == 2
    assert first not in results
    assert second in results
    assert third in results


@pytest.mark.asyncio
async def test_meeting_date_filter_keys_off_activity_not_creation():
    # Regression for #8839: meetings are indexed when scheduled, often weeks before they happen,
    # so a Content row for a recent meeting can carry an old created_at. A date-bounded search
    # must find it by its activity time (updated_at), not the stale created_at.
    now = datetime.now(UTC).replace(microsecond=0)
    organization = await create_organization()
    user = await create_user(organization=organization)

    meeting = await Meeting.create(
        title="Quarterly Planning Sync",
        organization_id=organization.id,
        creator_id=user.id,
        scheduled_at=now,
        summary="Planned the roadmap for the coming quarter.",
    )
    await ContentIndexingJob.from_model(organization.id, meeting).perform()

    content = await Content.get(source_id=str(meeting.global_id))
    # Backdate created_at to simulate the row being indexed weeks before the meeting occurred.
    await Content.filter(id=content.id).update(created_at=now - timedelta(days=30))

    results = await ContentResearchQuery(
        organization=organization, query="planning", user=user, starts_at=now - timedelta(days=7)
    ).execute()
    assert any(result.source_id == str(meeting.global_id) for result in results)


@pytest.mark.asyncio
async def test_searching_access_control():
    organization = await create_organization()
    first_user = await create_user(organization_id=organization.id)
    second_user = await create_user(organization_id=organization.id)

    first = await create_content(organization=organization)
    await first.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    second = await create_content(organization=organization)
    await second.indexer.index(
        SearchableData("Bananas", "Bananas are a yellow fruit", "https://example.com/bananas", "Bob Clams"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST_COMMENT,
            force_sharing=Sharing.PRIVATE,
            allowed_user_ids=[first_user.id],
        ),
    )

    third = await create_content(organization=organization)
    await third.indexer.index(
        SearchableData("Oranges", "Oranges are an orange fruit", "https://example.com/oranges", "Bob Clams"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST_COMMENT,
            force_sharing=Sharing.PRIVATE,
            allowed_user_ids=[first_user.id, second_user.id],
        ),
    )

    results = await ContentResearchQuery(organization=organization, query="fruit").execute()
    assert len(results) == 1
    assert first in results
    assert second not in results
    assert third not in results

    results = await ContentResearchQuery(organization=organization, query="fruit", user=first_user).execute()
    assert len(results) == 3
    assert first in results
    assert second in results
    assert third in results

    results = await ContentResearchQuery(organization=organization, query="fruit", user=second_user).execute()
    assert len(results) == 2
    assert first in results
    assert second not in results
    assert third in results


@pytest.mark.asyncio
async def test_indexing_permissions():
    organization = await create_organization()
    content = Content(source_id="unique_id_1", organization=organization, updated_at=datetime.now())
    await content.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, default_sharing=Sharing.PRIVATE),
    )
    await content.refresh_from_db()
    assert content.sharing.is_private

    await content.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, force_sharing=Sharing.ORGANIZATION),
    )
    await content.refresh_from_db()
    assert content.sharing.is_organization

    await content.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, default_sharing=Sharing.PRIVATE),
    )
    await content.refresh_from_db()
    assert content.sharing.is_organization


@pytest.mark.asyncio
async def test_sanitize_null_bytes():
    organization = await create_organization()
    content = Content(source_id="unique_id_2", organization=organization, updated_at=datetime.now())

    title_with_nulls = "Document\x00 with nulls"
    content_with_nulls = "This is content\x00 with null bytes\x00 that would cause PostgreSQL errors"
    author_with_nulls = "Author\x00 Name"

    await content.indexer.index(
        SearchableData(
            title_with_nulls, content_with_nulls, "https://example.com/document", author_with_nulls, content_with_nulls
        ),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    await content.refresh_from_db()
    assert "\x00" not in content.title
    assert content.title == "Document with nulls"
    assert "\x00" not in content.index_content
    assert content.index_content == "This is content with null bytes that would cause PostgreSQL errors"
    assert content.author is not None and "\x00" not in content.author
    assert content.author == "Author Name"

    results = await ContentResearchQuery(organization=organization, query="null bytes").execute()
    assert len(results) == 1
    assert results[0].id == content.id


@pytest.mark.asyncio
async def test_minimum_results_with_exact_matching_fallback():
    organization = await create_organization()
    first = await create_content(organization=organization)
    await first.indexer.index(
        SearchableData("Apple Pie", "Apple pie is a delicious dessert", "https://example.com/apple-pie", "Chef Baker"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )
    second = await create_content(organization=organization)
    await second.indexer.index(
        SearchableData(
            "Banana Bread", "Banana bread recipe with walnuts", "https://example.com/banana-bread", "Chef Baker"
        ),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )
    third = await create_content(organization=organization)
    await third.indexer.index(
        SearchableData(
            "Cherry Cobbler", "Cherry cobbler is a summer dessert", "https://example.com/cherry-cobbler", "Chef Baker"
        ),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )
    fourth = await create_content(organization=organization)
    await fourth.indexer.index(
        SearchableData("Peach Crisp", "Peach crisp with cinnamon", "https://example.com/peach-crisp", "Chef Baker"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    # Search with exact phrase matching that will only find 1 result (below threshold)
    results = await ContentResearchQuery(
        organization=organization, query='"delicious dessert"', minimum_results_with_exact_matching=2
    ).execute()
    assert len(results) > 1
    assert results[0].id == first.id
    assert any(r.id == third.id for r in results)

    # Set a high threshold to ensure it gets all available matches
    results = await ContentResearchQuery(
        organization=organization, query='"summer dessert"', minimum_results_with_exact_matching=10
    ).execute()
    assert len(results) > 1
    assert results[0].id == third.id


@pytest.mark.asyncio
async def test_basic_content_lookup():
    organization = await create_organization()
    first = await create_content(organization=organization)
    await first.indexer.index(
        SearchableData("Python Programming", "Learn Python basics", "https://example.com/python", "Jane Doe"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    second = await create_content(organization=organization)
    await second.indexer.index(
        SearchableData("JavaScript Guide", "Learn JavaScript", "https://example.com/js", "John Smith"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    # Full-text prefix match
    results = await ContentLookupQuery(organization=organization, query="Pyth").execute()
    assert len(results) == 1
    assert results[0].id == first.id

    # Full match
    results = await ContentLookupQuery(organization=organization, query="Python").execute()
    assert len(results) == 1
    assert results[0].id == first.id

    # No match
    results = await ContentLookupQuery(organization=organization, query="Ruby").execute()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_content_lookup_with_typos():
    organization = await create_organization()
    content = await create_content(organization=organization)
    await content.indexer.index(
        SearchableData("PostgreSQL Database", "Database management", "https://example.com/postgres", "Tech Writer"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    # Full-text prefix search matches partial words
    results = await ContentLookupQuery(organization=organization, query="Postgre").execute()
    assert len(results) == 1
    assert results[0].id == content.id


@pytest.mark.asyncio
async def test_content_lookup_with_partial_words():
    organization = await create_organization()
    content = await create_content(organization=organization)
    await content.indexer.index(
        SearchableData("Machine Learning Tutorial", "Introduction to ML", "https://example.com/ml", "AI Researcher"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    # Full-text search should handle partial last word
    results = await ContentLookupQuery(organization=organization, query="Machine Lear").execute()
    assert len(results) == 1
    assert results[0].id == content.id

    results = await ContentLookupQuery(organization=organization, query="machine learn").execute()
    assert len(results) == 1
    assert results[0].id == content.id


@pytest.mark.asyncio
async def test_content_lookup_stopword_query_falls_back_to_trigram():
    """`will` is an English stopword, so websearch_to_tsquery is empty and the full-text match finds
    nothing. The empty result triggers a title/author trigram fallback — the common first-name case."""
    organization = await create_organization()
    # Stopword in the title.
    will_title = await create_content(organization=organization)
    await will_title.indexer.index(
        SearchableData("Will Cheng", "Onboarding notes", "https://example.com/will", "Recruiting"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )
    # Stopword only in the AUTHOR (title unrelated) — the fallback matches and scores on author too,
    # so this must not collapse to 0 and vanish.
    will_author = await create_content(organization=organization)
    await will_author.indexer.index(
        SearchableData("Budget Report", "Numbers", "https://example.com/ba", "Will Ferrell"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )
    await (await create_content(organization=organization)).indexer.index(
        SearchableData("Quarterly Review", "Numbers", "https://example.com/q", "Finance"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    results = await ContentLookupQuery(organization=organization, query="will").execute()
    assert {r.id for r in results} == {will_title.id, will_author.id}

    # A non-stopword query still takes the full-text path (fallback never runs).
    exact = await ContentLookupQuery(organization=organization, query="budget").execute()
    assert {r.id for r in exact} == {will_author.id}

    # Below the 3-char gate an all-stopword query returns nothing rather than matching everything.
    assert await ContentLookupQuery(organization=organization, query="in").execute() == []


@pytest.mark.asyncio
async def test_content_lookup_stopword_fallback_escapes_like_metacharacters():
    """`will_can` is all-stopwords so it hits the trigram fallback; the `_` must match literally, not
    as a LIKE single-char wildcard, or it over-matches unrelated rows."""
    organization = await create_organization()
    literal = await create_content(organization=organization)
    await literal.indexer.index(
        SearchableData("will_can", "notes", "https://example.com/lit", "Author"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )
    bait = await create_content(organization=organization)
    await bait.indexer.index(
        SearchableData("willxcan", "notes", "https://example.com/bait", "Author"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    results = await ContentLookupQuery(organization=organization, query="will_can").execute()
    assert {r.id for r in results} == {literal.id}


@pytest.mark.asyncio
async def test_content_lookup_access_control():
    organization = await create_organization()
    first_user = await create_user(organization_id=organization.id)
    second_user = await create_user(organization_id=organization.id)

    org_content = await create_content(organization=organization)
    await org_content.indexer.index(
        SearchableData("Public Document", "Available to all", "https://example.com/public", "Author One"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    private_content = await create_content(organization=organization)
    await private_content.indexer.index(
        SearchableData("Private Document", "Restricted access", "https://example.com/private", "Author Two"),
        IndexMetadata(
            ContentCategory.DOCUMENT, ContentType.FILE, force_sharing=Sharing.PRIVATE, allowed_user_ids=[first_user.id]
        ),
    )

    # Without user, only org-level content
    results = await ContentLookupQuery(organization=organization, query="Doc").execute()
    assert len(results) == 1
    assert results[0].id == org_content.id

    # With authorized user, both
    results = await ContentLookupQuery(organization=organization, query="Doc", current_user=first_user).execute()
    assert len(results) == 2
    assert any(r.id == org_content.id for r in results)
    assert any(r.id == private_content.id for r in results)

    # With unauthorized user, only org-level
    results = await ContentLookupQuery(organization=organization, query="Doc", current_user=second_user).execute()
    assert len(results) == 1
    assert results[0].id == org_content.id


@pytest.mark.asyncio
async def test_content_lookup_normalization():
    organization = await create_organization()
    content = await create_content(organization=organization)
    await content.indexer.index(
        SearchableData("Résumé Builder", "Create professional resumes", "https://example.com/resume", "Career Coach"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    # Query with accents should match normalized content
    results = await ContentLookupQuery(organization=organization, query="Resume").execute()
    assert len(results) == 1
    assert results[0].id == content.id

    results = await ContentLookupQuery(organization=organization, query="Résumé").execute()
    assert len(results) == 1
    assert results[0].id == content.id

    # Case insensitive
    results = await ContentLookupQuery(organization=organization, query="RESUME").execute()
    assert len(results) == 1
    assert results[0].id == content.id


@pytest.mark.asyncio
async def test_content_lookup_deduplication():
    organization = await create_organization()
    content = await create_content(organization=organization)
    await content.indexer.index(
        SearchableData(
            "Python Programming Guide", "Python guide for beginners", "https://example.com/python", "Developer"
        ),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    # Query should deduplicate by lookup_key
    results = await ContentLookupQuery(organization=organization, query="Python").execute()
    assert len(results) == 1
    assert results[0].id == content.id


@pytest.mark.asyncio
async def test_content_lookup_recurring_meeting_deduplication():
    organization = await create_organization()
    user = await create_user(organization=organization)

    # Create 3 instances of a recurring meeting
    ical_uid = "recurring-standup-123"
    provider_meeting_id = "provider-standup-123"

    # First instance - no content
    meeting1 = await Meeting.create(
        title="Daily Standup",
        organization_id=organization.id,
        creator_id=user.id,
        ical_uid=ical_uid,
        provider_meeting_id=provider_meeting_id,
        scheduled_at=datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
    )
    await ContentIndexingJob.from_model(organization.id, meeting1).perform()

    # Second instance - has summary
    meeting2 = await Meeting.create(
        title="Daily Standup",
        organization_id=organization.id,
        creator_id=user.id,
        ical_uid=ical_uid,
        provider_meeting_id=provider_meeting_id,
        scheduled_at=datetime(2025, 1, 2, 9, 0, tzinfo=UTC),
        summary="Discussed progress on the project.",
    )
    await ContentIndexingJob.from_model(organization.id, meeting2).perform()

    # Third instance - has transcript (highest priority)
    meeting3 = await Meeting.create(
        title="Daily Standup",
        organization_id=organization.id,
        creator_id=user.id,
        ical_uid=ical_uid,
        provider_meeting_id=provider_meeting_id,
        scheduled_at=datetime(2025, 1, 3, 9, 0, tzinfo=UTC),
        processed_transcript=Transcript(
            lines=[
                TranscriptLine(line_number=0, speaker="Alice", content="Good morning!"),
                TranscriptLine(line_number=1, speaker="Bob", content="Hi everyone!"),
            ]
        ),
    )
    await ContentIndexingJob.from_model(organization.id, meeting3).perform()

    # Search for "standup" with user to have access
    results = await ContentLookupQuery(organization=organization, query="standup", current_user=user).execute()

    # Should only get ONE result (the highest priority instance)
    assert len(results) == 1

    # Should be the instance with transcript (meeting3)
    result_global_id = GlobalID.parse(results[0].source_id)
    assert result_global_id.record_id == meeting3.id

    # Verify all meetings were indexed with scheduled_at metadata
    meeting1_content = await Content.get(source_id=str(meeting1.global_id))
    assert meeting1_content.metadata.get("scheduled_at") == meeting1.scheduled_at

    meeting2_content = await Content.get(source_id=str(meeting2.global_id))
    assert meeting2_content.metadata.get("scheduled_at") == meeting2.scheduled_at

    meeting3_content = await Content.get(source_id=str(meeting3.global_id))
    assert meeting3_content.metadata.get("scheduled_at") == meeting3.scheduled_at


@pytest.mark.asyncio
async def test_content_lookup_exclusions():
    organization = await create_organization()
    user = await create_user(organization=organization)

    # Create meeting with a long transcript (will create chunks)
    long_transcript_text = "Speaker: " + " ".join(["word"] * 10000)
    meeting = await Meeting.create(
        title="Long Meeting",
        organization_id=organization.id,
        creator_id=user.id,
        scheduled_at=datetime.now(UTC),
        transcript=long_transcript_text,
        processed_transcript=Transcript(
            lines=[TranscriptLine(line_number=i, speaker="Speaker", content=f"Line {i}") for i in range(1000)]
        ),
    )
    await ContentIndexingJob.from_model(organization.id, meeting).perform()

    # Create some chat_history and post_comment content to verify they're excluded
    chat_history_content = await create_content(organization=organization)
    await chat_history_content.indexer.index(
        SearchableData("Long Meeting Chat", "This is chat history", "https://example.com/chat-history", "Chatter"),
        IndexMetadata(ContentCategory.ACTIVITY, ContentType.CHAT_HISTORY, Sharing.ORGANIZATION),
    )

    post_comment_content = await create_content(organization=organization)
    await post_comment_content.indexer.index(
        SearchableData(
            "Long Meeting Post Comment", "This is a post comment", "https://example.com/post-comment", "Commenter"
        ),
        IndexMetadata(ContentCategory.ACTIVITY, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    # Verify all content was created
    all_content = await Content.filter(organization_id=organization.id)
    transcript_chunks = [c for c in all_content if c.content_type == ContentType.MEETING_TRANSCRIPT]
    chat_histories = [c for c in all_content if c.content_type == ContentType.CHAT_HISTORY]
    post_comments = [c for c in all_content if c.content_type == ContentType.POST_COMMENT]

    assert len(transcript_chunks) > 0
    assert len(chat_histories) == 1
    assert len(post_comments) == 1

    # Search for "Long" - should only get the meeting, not transcripts or chat history
    results = await ContentLookupQuery(organization=organization, query="Long", current_user=user).execute()

    # Should only get the base meeting, not transcript chunks or chat history
    assert len(results) == 1
    assert results[0].content_type == ContentType.MEETING
    assert results[0].title == "Long Meeting"


@pytest.mark.asyncio
async def test_content_lookup_one_off_meeting_not_deduplicated():
    organization = await create_organization()
    user = await create_user(organization=organization)

    # Create 2 one-off meetings with same title
    meeting1 = await Meeting.create(
        title="Standalone Sync",
        organization_id=organization.id,
        creator_id=user.id,
        scheduled_at=datetime(2025, 1, 1, 14, 0, tzinfo=UTC),
    )
    await ContentIndexingJob.from_model(organization.id, meeting1).perform()

    meeting2 = await Meeting.create(
        title="Standalone Sync",
        organization_id=organization.id,
        creator_id=user.id,
        scheduled_at=datetime(2025, 1, 2, 14, 0, tzinfo=UTC),
    )
    await ContentIndexingJob.from_model(organization.id, meeting2).perform()

    # Search for the meeting title with user to have access
    results = await ContentLookupQuery(organization=organization, query="Standalone Sync", current_user=user).execute()

    # Should get BOTH meetings (they're not part of a series)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_content_lookup_with_special_characters():
    organization = await create_organization()
    content = await create_content(organization=organization)
    await content.indexer.index(
        SearchableData("Test Document", "Sample content", "https://example.com/test", "Author"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
    )

    # These should not cause tsquery syntax errors
    # The production error was: "from::*" when user typed "from:"
    results = await ContentLookupQuery(organization=organization, query="from:").execute()
    assert len(results) >= 0

    results = await ContentLookupQuery(organization=organization, query="test:*").execute()
    assert len(results) >= 0

    results = await ContentLookupQuery(organization=organization, query="hello & world").execute()
    assert len(results) >= 0

    results = await ContentLookupQuery(organization=organization, query="test | sample").execute()
    assert len(results) >= 0

    results = await ContentLookupQuery(organization=organization, query="!important").execute()
    assert len(results) >= 0


@pytest.mark.asyncio
async def test_content_lookup_recency_sorting():
    organization = await create_organization()
    now = datetime.now(UTC)

    # Create documents with same keyword but different ages
    old_doc = await create_content(organization=organization)
    await old_doc.indexer.index(
        SearchableData("Python Tutorial", "Old Python tutorial", "https://example.com/python-old", "Author"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.FILE,
            Sharing.ORGANIZATION,
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=30),
        ),
    )

    recent_doc = await create_content(organization=organization)
    await recent_doc.indexer.index(
        SearchableData("Python Guide", "Recent Python guide", "https://example.com/python-new", "Author"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.FILE,
            Sharing.ORGANIZATION,
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        ),
    )

    # Create an exact match that's older than both
    exact_match_old = await create_content(organization=organization)
    await exact_match_old.indexer.index(
        SearchableData("Python", "Old exact match for Python", "https://example.com/python-exact", "Author"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.FILE,
            Sharing.ORGANIZATION,
            created_at=now - timedelta(days=60),
            updated_at=now - timedelta(days=60),
        ),
    )

    # Full-text search sorts by ts_rank_cd * recency, so more recent content appears first
    results = await ContentLookupQuery(organization=organization, query="Python").execute()
    assert len(results) == 3
    # Most recent should come first due to recency multiplier
    assert results[0].id == recent_doc.id
    # Then older documents sorted by recency
    assert results[1].id == old_doc.id
    assert results[2].id == exact_match_old.id


@pytest.mark.asyncio
async def test_content_lookup_email_with_long_content():
    organization = await create_organization()

    # Create content with long text to test full-text search with email addresses
    long_content = " ".join([f"This is sentence {i} with lots of filler text." for i in range(100)])
    doc = await create_content(organization=organization)
    await doc.indexer.index(
        SearchableData(
            "Trip Confirmation Email",
            "Email about a trip confirmation",
            "https://example.com/email",
            "American Airlines <no-reply@info.email.aa.com>, "
            "Gerald Fontaine <gerald.fontaine@example.com>, "
            "Nadia Kirch <nadia.kirchner@example.com>",
            long_content,
        ),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.EMAIL_THREAD, Sharing.ORGANIZATION),
    )

    # Email search should find the document via full-text search
    results = await ContentLookupQuery(organization=organization, query="nadia.kirchner@example.com").execute()
    assert len(results) >= 1, "Should find document when searching by email address"
    assert any(r.id == doc.id for r in results), "Should find the specific document with that email"


@pytest.mark.asyncio
async def test_content_lookup_decay_multiplier():
    organization = await create_organization()
    now = datetime.now(UTC)

    # Doc 1: Very recent + high relevance → should rank #1 (wins on both factors)
    very_recent_high_rel = await create_content(organization=organization)
    await very_recent_high_rel.indexer.index(
        SearchableData(
            "Database Administration Complete Guide",
            "Comprehensive database administration guide covering all database topics",
            "https://example.com/db-recent-high",
            "Expert",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.FILE,
            Sharing.ORGANIZATION,
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        ),
    )
    await Content.filter(id=very_recent_high_rel.id).update(updated_at=now - timedelta(hours=1))

    # Doc 2: Very old + extremely high relevance → should rank #2 (relevance overcomes age)
    very_old_perfect_rel = await create_content(organization=organization)
    await very_old_perfect_rel.indexer.index(
        SearchableData(
            "Database Database Database Database Fundamentals",
            "Database database database systems database architecture database design "
            "database implementation database theory",
            "https://example.com/db-old-perfect",
            "DBA",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.FILE,
            Sharing.ORGANIZATION,
            created_at=now - timedelta(days=90),
            updated_at=now - timedelta(days=90),
        ),
    )
    await Content.filter(id=very_old_perfect_rel.id).update(updated_at=now - timedelta(days=90))

    # Doc 3: Medium age (7 days, half-life) + high relevance → should rank #3 (balanced)
    medium_age_high_rel = await create_content(organization=organization)
    await medium_age_high_rel.indexer.index(
        SearchableData(
            "Database Management Guide",
            "Practical database management techniques",
            "https://example.com/db-medium",
            "Engineer",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.FILE,
            Sharing.ORGANIZATION,
            created_at=now - timedelta(days=7),
            updated_at=now - timedelta(days=7),
        ),
    )
    await Content.filter(id=medium_age_high_rel.id).update(updated_at=now - timedelta(days=7))

    # Doc 4: Very old + medium relevance → should rank #4 (both factors against it)
    very_old_medium_rel = await create_content(organization=organization)
    await very_old_medium_rel.indexer.index(
        SearchableData(
            "Introduction to Database Concepts",
            "Basic overview of database",
            "https://example.com/db-old-medium",
            "Teacher",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.FILE,
            Sharing.ORGANIZATION,
            created_at=now - timedelta(days=120),
            updated_at=now - timedelta(days=120),
        ),
    )
    await Content.filter(id=very_old_medium_rel.id).update(updated_at=now - timedelta(days=120))

    # Query with partial word to test full-text search with recency
    results = await ContentLookupQuery(organization=organization, query="databa").execute()

    # All 4 docs should match
    assert len(results) == 4

    # Expected ordering verifies three key behaviors:
    # 1. Recency boost works: very recent wins overall
    # 2. Strong recency boost: medium age beats very old even with extreme relevance
    # 3. Both factors matter: very old with extreme relevance still beats very old with medium relevance
    assert results[0].id == very_recent_high_rel.id  # Best: both factors win
    assert results[1].id == medium_age_high_rel.id  # Medium age with decent relevance beats very old
    assert results[2].id == very_old_perfect_rel.id  # Extreme relevance keeps it above very old medium
    assert results[3].id == very_old_medium_rel.id  # Worst: both factors lose


@pytest.mark.asyncio
async def test_content_search_long_tail_text_matches():
    organization = await create_organization()

    with settings.override():
        # Restrict vector matches to 1 so only the top vector result comes through that path.
        # Text matches are set high enough to include all documents.
        settings.content_search_max_vector_matches = 1
        settings.content_search_max_text_matches = 20

        # Create a document about cooking - strong vector match for "chocolate cake"
        cooking_doc = await create_content(organization=organization)
        await cooking_doc.indexer.index(
            SearchableData(
                "Ultimate Chocolate Cake Recipe Guide",
                "The best chocolate cake recipe with rich chocolate frosting and ganache",
                "https://example.com/cooking",
                "Chef",
            ),
            IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
        )

        # Create a document about quantum physics that has NO keyword overlap with "chocolate cake"
        # This will rank via vector similarity only
        physics_doc = await create_content(organization=organization)
        await physics_doc.indexer.index(
            SearchableData(
                "Quantum Entanglement Research Paper",
                "Study of quantum entanglement and superposition in particle physics. "
                "Our approach to measurement techniques in quantum mechanics.",
                "https://example.com/quantum-physics",
                "Physicist",
            ),
            IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
        )

        # Create a document that has strong text match for the query but unrelated vector space
        text_strong_doc = await create_content(organization=organization)
        await text_strong_doc.indexer.index(
            SearchableData(
                "Music Production Techniques",
                "In music production, the chocolate cake recipe method is a mixing technique. "
                "The chocolate cake recipe approach ensures balanced frequencies. "
                "Apply the chocolate cake recipe to your master bus for warmth.",
                "https://example.com/music",
                "Producer",
            ),
            IndexMetadata(ContentCategory.DOCUMENT, ContentType.FILE, Sharing.ORGANIZATION),
        )

        results = await ContentResearchQuery(organization=organization, query="chocolate cake recipe").execute()
        result_ids = [r.id for r in results]

        # The cooking doc should always appear (strong vector + text match)
        assert cooking_doc.id in result_ids
        # The text-strong doc should appear via the text_matches UNION path even though
        # it would rank low in vector similarity (music production vs cooking)
        assert text_strong_doc.id in result_ids


#
# ContentLookup table read path
#
#


@pytest.mark.asyncio
@pytest.mark.disable_vcr
async def test_content_lookup_via_contentlookup_table():
    organization = await create_organization()
    content = await create_content(
        organization=organization,
        title="Python Programming",
        title_normalized="python programming",
        author="Jane Doe",
        author_normalized="jane doe",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
    )
    await ContentIndexer(content)._sync_content_lookup()

    results = await ContentLookupQuery(organization=organization, query="Pyth").execute()
    assert len(results) == 1
    assert results[0].id == content.id
    assert results[0].title == "Python Programming"
    assert results[0].source_global_id is not None


@pytest.mark.asyncio
@pytest.mark.disable_vcr
async def test_content_lookup_access_control_via_contentlookup_table():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    other_user = await create_user(organization_id=organization.id)

    org_content = await create_content(
        organization=organization,
        title="Shared Doc",
        title_normalized="shared doc",
        content_type=ContentType.FILE,
        sharing=Sharing.ORGANIZATION,
    )
    await ContentIndexer(org_content)._sync_content_lookup()

    private_content = await create_content(
        organization=organization,
        title="Private Doc",
        title_normalized="private doc",
        content_type=ContentType.FILE,
        sharing=Sharing.PRIVATE,
        allowed_user_ids=[str(user.id)],
    )
    await ContentIndexer(private_content)._sync_content_lookup()

    # Without user, only org-level
    results = await ContentLookupQuery(organization=organization, query="Doc").execute()
    assert len(results) == 1
    assert results[0].id == org_content.id

    # With authorized user, both
    results = await ContentLookupQuery(organization=organization, query="Doc", current_user=user).execute()
    assert len(results) == 2

    # With unauthorized user, only org-level
    results = await ContentLookupQuery(organization=organization, query="Doc", current_user=other_user).execute()
    assert len(results) == 1
    assert results[0].id == org_content.id


@pytest.mark.asyncio
async def test_content_lookup_person_results_not_crowded_out():
    organization = await create_organization()

    # Create a user content row (person result)
    user_content = await create_content(organization=organization)
    await user_content.indexer.index(
        SearchableData("Alice Smith", "Alice Smith\nalice@example.com", "User:alice", "Alice Smith"),
        IndexMetadata(
            ContentCategory.PERSON,
            ContentType.USER,
            force_sharing=Sharing.ORGANIZATION,
            updated_at=datetime.now(UTC) - timedelta(days=90),
        ),
    )

    # Create many recent non-person results that match the same query
    for i in range(15):
        content = await create_content(organization=organization)
        await content.indexer.index(
            SearchableData(
                f"Meeting with Alice {i}",
                f"Discussion with Alice about project {i}",
                f"https://example.com/meeting-{i}",
                "Alice Smith",
            ),
            IndexMetadata(
                ContentCategory.ACTIVITY,
                ContentType.MEETING,
                force_sharing=Sharing.ORGANIZATION,
                updated_at=datetime.now(UTC) - timedelta(hours=i),
            ),
        )

    results = await ContentLookupQuery(organization=organization, query="Alice", limit=10).execute()
    result_types = [r.content_type for r in results]

    # User result should appear despite being 90 days old
    assert ContentType.USER in result_types

    # Person slots are skipped when content_types is explicitly set
    results = await ContentLookupQuery(
        organization=organization,
        query="Alice",
        limit=10,
        content_types=[ContentType.MEETING],
    ).execute()
    result_types = [r.content_type for r in results]
    assert ContentType.USER not in result_types
    assert all(rt == ContentType.MEETING for rt in result_types)


@pytest.mark.asyncio
async def test_content_lookup_deranks_automated_sender():
    organization = await create_organization()

    human_thread = await create_content(organization=organization)
    await human_thread.indexer.index(
        SearchableData(
            "Budget Review",
            "The quarterly budget review discussion",
            "https://example.com/human",
            "Alice",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            is_automated_sender=False,
        ),
    )

    automated_thread = await create_content(organization=organization)
    await automated_thread.indexer.index(
        SearchableData(
            "Budget Review",
            "The quarterly budget review discussion",
            "https://example.com/bot",
            "noreply@example.com",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            is_automated_sender=True,
        ),
    )

    results = await ContentLookupQuery(organization=organization, query="Budget Review").execute()
    result_ids = [r.id for r in results]

    assert human_thread.id in result_ids
    assert automated_thread.id in result_ids
    assert result_ids.index(human_thread.id) < result_ids.index(automated_thread.id)


@pytest.mark.asyncio
async def test_content_lookup_deranks_calendar_invite():
    organization = await create_organization()

    regular_thread = await create_content(organization=organization)
    await regular_thread.indexer.index(
        SearchableData(
            "Product Kickoff",
            "Planning the product kickoff agenda",
            "https://example.com/plain",
            "Alice",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            has_calendar_invite=False,
        ),
    )

    invite_thread = await create_content(organization=organization)
    await invite_thread.indexer.index(
        SearchableData(
            "Product Kickoff",
            "Planning the product kickoff agenda",
            "https://example.com/invite",
            "Alice",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            has_calendar_invite=True,
        ),
    )

    results = await ContentLookupQuery(organization=organization, query="Product Kickoff").execute()
    result_ids = [r.id for r in results]

    assert regular_thread.id in result_ids
    assert invite_thread.id in result_ids
    assert result_ids.index(regular_thread.id) < result_ids.index(invite_thread.id)


@pytest.mark.asyncio
async def test_content_lookup_sorts_email_contacts_by_interaction_recency():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)

    now = datetime.now(UTC)

    # The stale contact was recently updated (e.g. the nightly contact sync refreshed
    # their display name or photo) but the user hasn't emailed them in months.
    # The fresh contact's record hasn't been touched in ages, but the user emailed
    # them a couple of hours ago. Interaction recency should win over record updated_at.
    stale = await create_email_contact(
        email="stale.smith@example.com",
        name="Stale Smith",
        organization_id=organization.id,
        user_id=user.id,
        updated_at=now - timedelta(hours=1),
        last_interacted_at=now - timedelta(days=180),
    )
    fresh = await create_email_contact(
        email="fresh.smith@example.com",
        name="Fresh Smith",
        organization_id=organization.id,
        user_id=user.id,
        updated_at=now - timedelta(days=90),
        last_interacted_at=now - timedelta(hours=2),
    )

    for contact in (stale, fresh):
        indexing_id = IndexingID(organization_id=organization.id, source_id=str(contact.global_id))
        await IndexEmailContactJob(indexing_id=indexing_id).perform()

    results = await ContentLookupQuery(organization=organization, query="Smith", current_user=user).execute()
    result_ids = [r.id for r in results]

    stale_content = await Content.filter(source_id=str(stale.global_id)).get()
    fresh_content = await Content.filter(source_id=str(fresh.global_id)).get()

    assert stale_content.id in result_ids
    assert fresh_content.id in result_ids
    assert result_ids.index(fresh_content.id) < result_ids.index(stale_content.id)


@pytest.mark.asyncio
async def test_indexing_new_empty_content_does_not_violate_lookup_fk(caplog):
    # Regression: a freshly created, still-blank document (e.g. an empty meeting
    # agenda) gets indexed before any text is typed. The Content row does not
    # exist yet and index_content is empty, so the indexer takes the
    # empty-content early return. That branch must not try to sync a
    # ContentLookup against an unsaved Content — doing so inserts a row whose
    # content_id has no matching content row and raises the foreign-key
    # violation contentlookup_content_id_fkey (silently swallowed in prod).
    organization = await create_organization()
    indexing_id = IndexingID(organization_id=organization.id, source_id="https://example.com/blank-agenda")

    indexer = await indexing_id.fetch_indexer()
    assert indexer.content.is_new

    with caplog.at_level(logging.ERROR):
        await indexer.index(
            SearchableData(title="Blank Agenda", index_content="", url="https://example.com/blank-agenda"),
            IndexMetadata(ContentCategory.DOCUMENT, ContentType.DOCUMENT, Sharing.ORGANIZATION),
        )

    assert "Failed to sync content lookup entry" not in caplog.text
    assert await ContentLookup.filter(content_id=indexer.content.id).exists() is False
