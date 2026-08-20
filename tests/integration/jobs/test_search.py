from uuid import uuid4

import pytest

from app.jobs.search import SearchDiagnosticJob
from app.models.collaboration.content import (
    IndexMetadata,
    SearchableData,
    run_lookup_search,
    run_serp_search,
)
from config.enums import ContentCategory, ContentType, Sharing
from tests.helpers.factories import create_content, create_organization, create_user

pytestmark = pytest.mark.real_embeddings


async def _index(
    content,
    title,
    body,
    url,
    *,
    sharing=Sharing.ORGANIZATION,
    allowed_user_ids=None,
    content_type=ContentType.DOCUMENT,
    category=ContentCategory.DOCUMENT,
):
    await content.indexer.index(
        SearchableData(title, body, url, "Alice"),
        IndexMetadata(
            category,
            content_type,
            force_sharing=sharing,
            allowed_user_ids=allowed_user_ids,
        ),
    )


@pytest.mark.asyncio
async def test_serp_diagnostics_localize_drops_and_funnel():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    other_user = await create_user(organization_id=organization.id)

    hit = await create_content(organization=organization)
    await _index(hit, "Quarterly Budget Report", "The quarterly budget report", "https://ex.com/1")

    private = await create_content(organization=organization)
    await _index(
        private,
        "Quarterly Budget Secret",
        "Confidential budget figures",
        "https://ex.com/2",
        sharing=Sharing.PRIVATE,
        allowed_user_ids=[other_user.id],
    )

    meeting = await create_content(organization=organization)
    await _index(
        meeting,
        "Quarterly Budget Sync",
        "Discuss the budget",
        "https://ex.com/3",
        content_type=ContentType.MEETING,
        category=ContentCategory.ACTIVITY,
    )

    results, search = await run_serp_search(
        organization=organization, query="quarterly budget", user=user, collect_diagnostics=True
    )
    result_ids = [r.id for r in results]

    # An accessible, strongly matching item is returned and scored.
    returned = await search.diagnose_target(hit.id, result_ids)
    assert returned.exists and returned.accessible and returned.text_matches and returned.above_floor
    assert returned.rank is not None
    assert returned.verdict.startswith("returned at rank")
    assert search.component_scores[hit.id]["relevance_score"] is not None

    # Private-to-another-user content is dropped at the access stage — the privacy answer.
    blocked = await search.diagnose_target(private.id, result_ids)
    assert blocked.accessible is False
    assert "access control" in blocked.verdict
    assert private.id not in result_ids

    # A non-existent id is reported as such.
    missing = await search.diagnose_target(uuid4(), result_ids)
    assert missing.exists is False

    # An org-shared, in-type item that was never indexed (zero embedding → NaN similarity) is
    # reported as missing an embedding, not mislabeled as "below the relevance floor".
    unembedded = await create_content(
        organization=organization, title="Quarterly Budget Draft", content_type=ContentType.DOCUMENT
    )
    no_embedding = await search.diagnose_target(unembedded.id, result_ids)
    assert no_embedding.relevance_score is None
    assert "no embedding" in no_embedding.verdict

    # Funnel collapses monotonically through every stage, including the content_type stage.
    funnel = await search.funnel()
    assert (
        funnel["organization_total"]
        >= funnel["matching_content_types"]
        >= funnel["accessible"]
        >= funnel["text_matching"]
        >= 2
    )
    assert "budget" in await search.generated_tsquery()

    # Scoping to documents drops the matching meeting at the content_type stage.
    _, scoped = await run_serp_search(
        organization=organization,
        query="quarterly budget",
        user=user,
        content_type=ContentType.DOCUMENT,
        collect_diagnostics=True,
    )
    typed_out = await scoped.diagnose_target(meeting.id)
    assert typed_out.content_type_included is False
    assert "content_type" in typed_out.verdict


@pytest.mark.asyncio
async def test_lookup_diagnostics_localize_drops():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    other_user = await create_user(organization_id=organization.id)

    hit = await create_content(organization=organization)
    await _index(hit, "Roadmap Planning Doc", "Roadmap planning notes", "https://ex.com/r1")

    private = await create_content(organization=organization)
    await _index(
        private,
        "Roadmap Secret",
        "Secret roadmap",
        "https://ex.com/r2",
        sharing=Sharing.PRIVATE,
        allowed_user_ids=[other_user.id],
    )

    # Created directly (not indexed), so no ContentLookup row exists for it.
    unsynced = await create_content(
        organization=organization, title="Roadmap Unsynced", index_content="roadmap unsynced"
    )

    results, lookup = await run_lookup_search(
        organization=organization, query="roadmap", user=user, collect_diagnostics=True
    )
    result_ids = [r.id for r in results]

    returned = await lookup.diagnose_target(hit.id, result_ids)
    assert returned.exists and returned.accessible and returned.text_matches
    assert returned.rank is not None
    assert lookup.result_scores.get(hit.id) is not None

    blocked = await lookup.diagnose_target(private.id, result_ids)
    assert blocked.accessible is False
    assert "access control" in blocked.verdict

    # Content present but never synced to the lookup table — a real "lookup empty" cause.
    not_synced = await lookup.diagnose_target(unsynced.id, result_ids)
    assert "not synced to ContentLookup" in not_synced.verdict

    funnel = await lookup.funnel()
    assert funnel["organization_total"] >= funnel["accessible"] >= funnel["text_matching"] >= 1
    assert await lookup.generated_tsquery()


@pytest.mark.asyncio
async def test_lookup_diagnostics_reflect_stopword_fallback():
    """For an all-stopword query the diagnostic must reflect the query that actually ran: the trigram
    fallback returns the row, so the report can't simultaneously report empty/no-match for it."""
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    will = await create_content(organization=organization)
    await _index(will, "Will Cheng", "Onboarding", "https://ex.com/will")

    results, lookup = await run_lookup_search(
        organization=organization, query="will", user=user, collect_diagnostics=True
    )
    result_ids = [r.id for r in results]
    assert will.id in result_ids

    # tsquery shows the real (empty, all-stopword) query; the fallback is its own honest signal.
    assert lookup.used_trigram_fallback is True
    assert await lookup.generated_tsquery() == ""
    assert (await lookup.funnel())["text_matching"] >= 1
    target = await lookup.diagnose_target(will.id, result_ids)
    assert target.text_matches
    assert target.verdict.startswith("returned at rank")


@pytest.mark.asyncio
async def test_search_diagnostic_job_resolves_expected_and_runs():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    doc = await create_content(organization=organization)
    await _index(doc, "Acme Launch Plan", "Launch plan for Acme", "https://ex.com/a")

    job = SearchDiagnosticJob(user_email=user.email, query="acme launch", expected=["Acme Launch Plan"])

    # Expected matchers resolve by title substring, exact id, and source_url.
    assert doc.id in await job._resolve_matcher(organization.id, "Acme Launch")
    assert await job._resolve_matcher(organization.id, str(doc.id)) == [doc.id]
    assert doc.id in await job._resolve_matcher(organization.id, "https://ex.com/a")

    # End to end: both search types run and log without error.
    await job.perform()

    # A missing user is handled gracefully (no raise).
    await SearchDiagnosticJob(user_email="nobody@example.com", query="acme launch").perform()
