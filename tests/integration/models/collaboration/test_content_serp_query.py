from datetime import UTC, datetime, timedelta

import pytest

from app.models.collaboration.content import (
    ContentSerpQuery,
    IndexMetadata,
    SearchableData,
)
from config.enums import ContentCategory, ContentType, Sharing
from tests.helpers.factories import create_content, create_organization

pytestmark = pytest.mark.real_embeddings


@pytest.mark.asyncio
async def test_serp_title_match_ranks_higher():
    organization = await create_organization()

    # Content with query terms only in body
    body_match = await create_content(organization=organization)
    await body_match.indexer.index(
        SearchableData(
            "Unrelated Title",
            "The quarterly budget report shows increased spending",
            "https://example.com/1",
            "Alice",
        ),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.DOCUMENT, Sharing.ORGANIZATION),
    )

    # Content with query terms in title
    title_match = await create_content(organization=organization)
    await title_match.indexer.index(
        SearchableData(
            "Budget Report",
            "This document covers various topics",
            "https://example.com/2",
            "Alice",
        ),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.DOCUMENT, Sharing.ORGANIZATION),
    )

    results = await ContentSerpQuery(organization=organization, query="budget report").execute()
    result_ids = [r.id for r in results]

    assert title_match.id in result_ids
    assert body_match.id in result_ids
    assert result_ids.index(title_match.id) < result_ids.index(body_match.id)


@pytest.mark.asyncio
async def test_serp_recency_boosts_ranking():
    now = datetime.now(UTC).replace(microsecond=0)
    organization = await create_organization()

    old_content = await create_content(organization=organization)
    await old_content.indexer.index(
        SearchableData("Project Update", "Status of the project", "https://example.com/old", "Alice"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.DOCUMENT,
            Sharing.ORGANIZATION,
            updated_at=now - timedelta(days=180),
        ),
    )

    recent_content = await create_content(organization=organization)
    await recent_content.indexer.index(
        SearchableData("Project Update", "Status of the project", "https://example.com/recent", "Alice"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.DOCUMENT,
            Sharing.ORGANIZATION,
            updated_at=now,
        ),
    )

    results = await ContentSerpQuery(organization=organization, query="project update").execute()
    result_ids = [r.id for r in results]

    assert recent_content.id in result_ids
    assert old_content.id in result_ids
    assert result_ids.index(recent_content.id) < result_ids.index(old_content.id)


@pytest.mark.asyncio
async def test_serp_unified_ranking_no_category_partitioning():
    organization = await create_organization()

    # Create content across different categories, all matching the same query
    activity = await create_content(organization=organization)
    await activity.indexer.index(
        SearchableData("Weekly Standup", "Discussed the roadmap", "https://example.com/meeting", "Alice"),
        IndexMetadata(ContentCategory.ACTIVITY, ContentType.MEETING, Sharing.ORGANIZATION),
    )

    document = await create_content(organization=organization)
    await document.indexer.index(
        SearchableData("Roadmap Document", "The product roadmap for Q3", "https://example.com/doc", "Alice"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.DOCUMENT, Sharing.ORGANIZATION),
    )

    # Results should be in a single ranked list, not partitioned by category
    results = await ContentSerpQuery(organization=organization, query="roadmap").execute()
    assert len(results) >= 2
    result_ids = [r.id for r in results]
    assert document.id in result_ids
    assert activity.id in result_ids


@pytest.mark.asyncio
async def test_serp_content_type_filtering():
    organization = await create_organization()

    meeting = await create_content(organization=organization)
    await meeting.indexer.index(
        SearchableData("Design Review", "Review of the new design", "https://example.com/meeting", "Alice"),
        IndexMetadata(ContentCategory.ACTIVITY, ContentType.MEETING, Sharing.ORGANIZATION),
    )

    post = await create_content(organization=organization)
    await post.indexer.index(
        SearchableData("Design Review Summary", "Summary of the design review", "https://example.com/post", "Alice"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST, Sharing.ORGANIZATION),
    )

    results = await ContentSerpQuery(
        organization=organization, query="design review", content_types={ContentType.POST}
    ).execute()
    result_ids = [r.id for r in results]

    assert post.id in result_ids
    assert meeting.id not in result_ids


@pytest.mark.asyncio
async def test_serp_access_control():
    organization = await create_organization()

    public_content = await create_content(organization=organization)
    await public_content.indexer.index(
        SearchableData("Public Doc", "Available to all org members", "https://example.com/public", "Alice"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.DOCUMENT, Sharing.ORGANIZATION),
    )

    # Without a user, only organization-shared content is returned
    results = await ContentSerpQuery(organization=organization, query="public doc").execute()
    assert len(results) == 1
    assert results[0].id == public_content.id


@pytest.mark.asyncio
async def test_serp_hero_promotion():
    now = datetime.now(UTC).replace(microsecond=0)
    organization = await create_organization()

    # High relevance but old — exact title match from 6 months ago
    hero_candidate = await create_content(organization=organization)
    await hero_candidate.indexer.index(
        SearchableData(
            "Onboarding Guide",
            "The complete onboarding guide for new team members",
            "https://example.com/guide",
            "Alice",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.DOCUMENT,
            Sharing.ORGANIZATION,
            updated_at=now - timedelta(days=180),
        ),
    )

    # Low relevance but recent — only mentions onboarding in body
    recent_noise = await create_content(organization=organization)
    await recent_noise.indexer.index(
        SearchableData(
            "Weekly Team Sync",
            "Discussed onboarding timeline for the new hire",
            "https://example.com/sync",
            "Alice",
        ),
        IndexMetadata(
            ContentCategory.ACTIVITY,
            ContentType.MEETING,
            Sharing.ORGANIZATION,
            updated_at=now,
        ),
    )

    search = ContentSerpQuery(organization=organization, query="onboarding guide")
    results = await search.execute()

    # Recency pushes the recent noise above the hero candidate
    assert results[0].id == recent_noise.id

    # Hero promotion rescues the high-relevance result to position 1
    results = search.promote_heroes(results)
    assert results[0].id == hero_candidate.id


@pytest.mark.asyncio
async def test_serp_deranks_automated_sender_content():
    organization = await create_organization()

    human_thread = await create_content(organization=organization)
    await human_thread.indexer.index(
        SearchableData(
            "Budget Review", "The quarterly budget review discussion", "https://example.com/human", "Alice"
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
            "Budget Review", "The quarterly budget review discussion", "https://example.com/bot", "noreply@example.com"
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            is_automated_sender=True,
        ),
    )

    results = await ContentSerpQuery(organization=organization, query="budget review").execute()
    result_ids = [r.id for r in results]

    assert human_thread.id in result_ids
    assert automated_thread.id in result_ids
    assert result_ids.index(human_thread.id) < result_ids.index(automated_thread.id)


@pytest.mark.asyncio
async def test_serp_deranks_calendar_invite_content():
    organization = await create_organization()

    regular_thread = await create_content(organization=organization)
    await regular_thread.indexer.index(
        SearchableData("Product Kickoff", "Planning the product kickoff agenda", "https://example.com/plain", "Alice"),
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
            "Product Kickoff", "Planning the product kickoff agenda", "https://example.com/invite", "Alice"
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            has_calendar_invite=True,
        ),
    )

    results = await ContentSerpQuery(organization=organization, query="product kickoff").execute()
    result_ids = [r.id for r in results]

    assert regular_thread.id in result_ids
    assert invite_thread.id in result_ids
    assert result_ids.index(regular_thread.id) < result_ids.index(invite_thread.id)


@pytest.mark.asyncio
async def test_serp_hero_promotion_respects_derank():
    now = datetime.now(UTC).replace(microsecond=0)
    organization = await create_organization()

    # High raw relevance (title match) but automated and old — without the
    # derank folded into the stored relevance_score, promote_heroes would
    # rescue this to position 1 even though the ORDER BY pushes it down.
    automated_thread = await create_content(organization=organization)
    await automated_thread.indexer.index(
        SearchableData(
            "Onboarding Guide",
            "The complete onboarding guide for new team members",
            "https://example.com/automated",
            "noreply@example.com",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            updated_at=now - timedelta(days=180),
            is_automated_sender=True,
        ),
    )

    # Recent human email with weaker (body-only) match
    recent_human = await create_content(organization=organization)
    await recent_human.indexer.index(
        SearchableData(
            "Weekly Team Sync",
            "Discussed onboarding timeline for the new hire",
            "https://example.com/human",
            "Alice",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            updated_at=now,
        ),
    )

    search = ContentSerpQuery(organization=organization, query="onboarding guide")
    results = await search.execute()

    # Derank + recency keep the automated email below the recent human
    assert results[0].id == recent_human.id

    # promote_heroes must not rescue the automated email — its stored
    # relevance_score reflects the 0.25× derank, closing the gap below
    # SERP_HERO_RELEVANCE_GAP
    results = search.promote_heroes(results)
    assert results[0].id == recent_human.id
