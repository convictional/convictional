import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import sentry_sdk
from freezegun import freeze_time

from app.jobs.mailers import SendResearchQuestionEmailJob
from app.jobs.research import (
    CheckScheduledResearchJob,
    GeneratedResearchQuery,
    PrepareScheduledResearchJob,
    PublishScheduledResearchJob,
    ResearchJob,
    ResearchQueryJob,
    ResearchQuestionCompleteJob,
    ScheduledResearchJob,
)
from app.mailers.research import ResearchQuestionMailer, ScheduledResearchMailer
from app.models.accounts import OAuthToken
from app.models.collaboration.content import (
    ContentLookupQuery,
    ContentResearchQuery,
    IndexMetadata,
    Research,
    ResearchIteration,
    ResearchQuery,
    SearchableData,
)
from app.models.commands import ResearchQuestion, ScheduledResearchDelivery
from config import settings
from config.enums import (
    AuthenticationProvider,
    ContentCategory,
    ContentType,
    Integration,
    ResearchSource,
    Sharing,
)
from infra.email import fake_delivery
from infra.jobs import InlineJobs, JobsOutbox
from infra.llm import DEFAULT_MODEL
from tests.helpers.factories import (
    create_content,
    create_research,
    create_research_question,
    create_scheduled_research,
    create_user,
)

pytestmark = pytest.mark.real_embeddings


@pytest.mark.asyncio
async def test_research_job():
    user = await create_user()
    await user.fetch_related("organization")

    # Content IDs are hardcoded to ensure the same content is used in the cassette request bodies
    first = await create_content(id="20b1d2d7-f11f-48d5-a709-a24dd8e728b1", organization=user.organization)
    await first.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    second = await create_content(id="65fe6aa2-f247-41b3-9f61-b512f5e398c6", organization=user.organization)
    await second.indexer.index(
        SearchableData("Bananas", "Bananas are a yellow fruit", "https://example.com/bananas", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    third = await create_content(id="3868846f-4ac6-4cd3-9815-868c85d19e47", organization=user.organization)
    await third.indexer.index(
        SearchableData("Oranges", "Oranges are an orange fruit", "https://example.com/oranges", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    research = await Research.create(
        topic="Kinds and colours of fruits",
        sources=[ResearchSource.INTERNAL],
        max_depth=2,
        max_breadth=3,
        creator_id=user.id,
        organization_id=user.organization_id,
    )

    async with JobsOutbox():
        await ResearchJob(research_id=research.id).perform()

    # With max_depth=2, the recursive tree fans out:
    # - 1 iteration at depth=0 with N queries (N is LLM-determined, up to max_breadth)
    # - N iterations at depth=1, one per depth-0 query (each query branches independently)
    # The recorded cassette produces 2 queries at depth=0, so we expect 4 iterations total.
    iterations = await ResearchIteration.all().prefetch_related("queries")
    assert len(iterations) == 4
    assert all(iteration.research_id == research.id for iteration in iterations)

    depth_0_iterations = [i for i in iterations if i.depth == 0]
    depth_1_iterations = [i for i in iterations if i.depth == 1]

    # Exactly one iteration at depth 0
    assert len(depth_0_iterations) == 1
    first_iteration = depth_0_iterations[0]
    assert len(first_iteration.title) > 0
    assert first_iteration.directions == "Kinds and colours of fruits"
    assert first_iteration.queries_count == 3  # max_breadth
    assert len(first_iteration.queries) >= 2  # cassette produces 2
    assert all(query.is_completed for query in first_iteration.queries)
    assert all(len(query.title) > 0 for query in first_iteration.queries)
    assert all(len(query.goals) > 0 for query in first_iteration.queries)
    assert all(len(query.content_search_terms) > 0 for query in first_iteration.queries)
    assert all(query.source == ResearchSource.INTERNAL for query in first_iteration.queries)

    # Recursive tree: each depth-0 query spawns its own depth-1 iteration
    depth_0_queries = list(first_iteration.queries)
    assert len(depth_1_iterations) == len(depth_0_queries)

    for child_iteration in depth_1_iterations:
        assert len(child_iteration.title) > 0
        assert child_iteration.directions != first_iteration.directions
        assert len(child_iteration.queries) >= 1  # cassette produces 1 per depth-1 iteration
        assert all(query.is_completed for query in child_iteration.queries)
        assert all(len(query.title) > 0 for query in child_iteration.queries)
        assert all(len(query.goals) > 0 for query in child_iteration.queries)
        assert all(len(query.content_search_terms) > 0 for query in child_iteration.queries)
        assert all(query.source == ResearchSource.INTERNAL for query in child_iteration.queries)

    # Each depth-1 iteration should have unique directions (from different parent queries)
    depth_1_directions = [i.directions for i in depth_1_iterations]
    assert len(depth_1_directions) == len(set(depth_1_directions))

    # Test the research is completed
    await research.refresh_from_db()
    await research.fetch_related("iterations__queries")
    assert research.is_completed


@pytest.mark.asyncio
async def test_research_is_not_completed_until_all_iterations_have_spawned_their_children():
    # Race scenario observed in production: a single leaf branch finished before its sibling parent
    # query had spawned its own leaf iteration. The old is_completed checked only leaf-depth
    # iterations and returned True against the partial tree, firing publish on a half-done research.
    user = await create_user()
    await user.fetch_related("organization")

    research = await Research.create(
        topic="Fruit",
        sources=[ResearchSource.INTERNAL],
        max_depth=2,
        creator_id=user.id,
        organization_id=user.organization_id,
    )
    parent = await ResearchIteration.create(
        research=research, title="Planning", directions=research.topic, queries_count=2, depth=0
    )
    finished_parent_query = await ResearchQuery.create(
        title="Q1", goals="g", research=research, iteration=parent, source=ResearchSource.INTERNAL
    )
    in_flight_parent_query = await ResearchQuery.create(
        title="Q2", goals="g", research=research, iteration=parent, source=ResearchSource.INTERNAL
    )
    await finished_parent_query.mark_completed(learnings=["L1"])
    # in_flight_parent_query intentionally left incomplete — its child iteration has not been spawned.

    completed_child = await ResearchIteration.create(
        research=research, title="Child A", directions="x", queries_count=1, depth=1
    )
    completed_child_query = await ResearchQuery.create(
        title="QA1", goals="g", research=research, iteration=completed_child, source=ResearchSource.INTERNAL
    )
    await completed_child_query.mark_completed(learnings=["L2"])

    await research.fetch_related("iterations__queries")
    assert research.is_completed is False

    # Once Q2 also completes (and its child iteration finishes), the property flips to True.
    await in_flight_parent_query.mark_completed(learnings=["L3"])
    sibling_child = await ResearchIteration.create(
        research=research, title="Child B", directions="x", queries_count=1, depth=1
    )
    sibling_child_query = await ResearchQuery.create(
        title="QB1", goals="g", research=research, iteration=sibling_child, source=ResearchSource.INTERNAL
    )
    await sibling_child_query.mark_completed(learnings=["L4"])

    await research.fetch_related("iterations__queries")
    assert research.is_completed is True


@pytest.mark.asyncio
async def test_research_query_spawns_next_iteration_without_waiting_for_siblings():
    user = await create_user()
    await user.fetch_related("organization")

    # Content ID is hardcoded to ensure the same content is used in the cassette request bodies
    content = await create_content(id="f47ac10b-58cc-4372-a567-0e02b2c3d479", organization=user.organization)
    await content.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    # Create research and first iteration manually so we can control the state
    research = await Research.create(
        topic="Kinds of fruits",
        sources=[ResearchSource.INTERNAL],
        max_depth=2,
        max_breadth=2,
        creator_id=user.id,
        organization_id=user.organization_id,
    )
    iteration = await ResearchIteration.create(
        research=research,
        title="Planning",
        directions=research.topic,
        queries_count=2,
        depth=0,
    )

    # Pre-create an incomplete sibling query to simulate a concurrent query that hasn't finished yet.
    # This is the key: when the job re-fetches the iteration, it will see this incomplete sibling.
    await ResearchQuery.create(
        title="Sibling query",
        goals="Research different kinds of fruits",
        research=research,
        iteration=iteration,
        source=ResearchSource.INTERNAL,
    )

    # Build a GeneratedResearchQuery — this is what ResearchIterationJob would normally produce
    generated_query = GeneratedResearchQuery(
        title="Fruit colours",
        terms="fruit colours",
        goals="Research the colours of different fruits and what determines their colour",
    )

    # Run ResearchQueryJob directly — it creates its own query, searches, reviews, and decides
    # whether to branch into a child iteration
    async with JobsOutbox():
        await ResearchQueryJob(
            iteration_id=iteration.id,
            generated_query_data=generated_query.model_dump_json(),
        ).perform()

    # A child iteration at depth 1 should exist — in the recursive tree, each query branches
    # into its own child iteration immediately, without waiting for sibling queries to complete.
    child_iterations = await ResearchIteration.filter(research_id=research.id, depth=1).all()
    assert len(child_iterations) == 1
    assert child_iterations[0].depth == 1
    assert len(child_iterations[0].title) > 0


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@freeze_time("2025-06-15 12:00:00")
async def test_research_date_filtering():
    """Test that research correctly filters content by date ranges based on time-related queries."""
    frozen_now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    user = await create_user()
    await user.fetch_related("organization")

    # Create content at different points in time
    # Content from this week (3 days ago)
    this_week_content = await create_content(id="11111111-1111-1111-1111-111111111111", organization=user.organization)
    await this_week_content.indexer.index(
        SearchableData(
            "Weekly standup notes",
            "Team discussed sprint progress and blockers",
            "https://example.com/standup",
            "Alice",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST_COMMENT,
            Sharing.ORGANIZATION,
            created_at=frozen_now - timedelta(days=3),
        ),
    )

    # Content from last week (10 days ago)
    last_week_content = await create_content(id="22222222-2222-2222-2222-222222222222", organization=user.organization)
    await last_week_content.indexer.index(
        SearchableData(
            "Sprint retrospective",
            "Team reviewed what went well and areas for improvement",
            "https://example.com/retro",
            "Bob",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST_COMMENT,
            Sharing.ORGANIZATION,
            created_at=frozen_now - timedelta(days=10),
        ),
    )

    # Content from this quarter (45 days ago)
    this_quarter_content = await create_content(
        id="33333333-3333-3333-3333-333333333333", organization=user.organization
    )
    await this_quarter_content.indexer.index(
        SearchableData(
            "Q2 planning document",
            "Quarterly goals and objectives for the team",
            "https://example.com/q2-planning",
            "Carol",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST_COMMENT,
            Sharing.ORGANIZATION,
            created_at=frozen_now - timedelta(days=45),
        ),
    )

    # Content from last year (400 days ago)
    last_year_content = await create_content(id="44444444-4444-4444-4444-444444444444", organization=user.organization)
    await last_year_content.indexer.index(
        SearchableData(
            "Annual review 2024",
            "Company achievements and lessons learned from last year",
            "https://example.com/annual-review",
            "Dave",
        ),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST_COMMENT,
            Sharing.ORGANIZATION,
            created_at=frozen_now - timedelta(days=400),
        ),
    )

    async def run_research_and_get_queries(topic: str) -> list[ResearchQuery]:
        research = await Research.create(
            topic=topic,
            sources=[ResearchSource.INTERNAL],
            max_depth=1,
            max_breadth=1,
            creator_id=user.id,
            organization_id=user.organization_id,
        )
        async with JobsOutbox():
            await ResearchJob(research_id=research.id).perform()

        await research.fetch_related("iterations__queries")
        return research.all_queries

    # Test "this week" - should generate dates filtering to recent content
    this_week_queries = await run_research_and_get_queries("What did the team discuss this week about sprints?")
    assert len(this_week_queries) > 0
    # The LLM should have generated a starts_at date for "this week"
    assert any(q.starts_at is not None for q in this_week_queries), "Expected date filter for 'this week' query"
    # Check the date is within the last 7 days
    for query in this_week_queries:
        if query.starts_at:
            assert query.starts_at >= frozen_now - timedelta(days=7), "starts_at should be within last 7 days"

    # Test "last week" - should filter to ~7-14 days ago
    last_week_queries = await run_research_and_get_queries("What happened last week in team retrospectives?")
    assert len(last_week_queries) > 0
    assert any(q.starts_at is not None for q in last_week_queries), "Expected date filter for 'last week' query"

    # Test "this quarter" - should filter to last ~90 days
    this_quarter_queries = await run_research_and_get_queries("What are our quarterly planning goals this quarter?")
    assert len(this_quarter_queries) > 0
    assert any(q.starts_at is not None for q in this_quarter_queries), "Expected date filter for 'this quarter' query"
    for query in this_quarter_queries:
        if query.starts_at:
            assert query.starts_at >= frozen_now - timedelta(days=120), "starts_at should be within this quarter"

    # Test "last year" - should filter to previous year
    last_year_queries = await run_research_and_get_queries(
        "What were the company achievements from last year's review?"
    )
    assert len(last_year_queries) > 0
    assert any(q.starts_at is not None for q in last_year_queries), "Expected date filter for 'last year' query"

    # Test no date reference - should NOT generate date filters
    no_date_queries = await run_research_and_get_queries("What are the team's general processes for code reviews?")
    assert len(no_date_queries) > 0
    # When there's no time reference, dates should be None
    assert all(q.starts_at is None and q.ends_at is None for q in no_date_queries), (
        "Expected no date filters for query without time reference"
    )


@pytest.mark.asyncio
async def test_research_iteration_job_creates_individual_query_jobs(background_jobs: InlineJobs):
    user = await create_user()
    await user.fetch_related("organization")

    first = await create_content(organization=user.organization)
    await first.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    second = await create_content(organization=user.organization)
    await second.indexer.index(
        SearchableData("Bananas", "Bananas are a yellow fruit", "https://example.com/bananas", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    research = await Research.create(
        topic="Test fruits research",
        sources=[ResearchSource.INTERNAL],
        max_depth=1,  # Keep it simple
        max_breadth=2,
        creator_id=user.id,
        organization_id=user.organization_id,
    )

    async with JobsOutbox():
        await ResearchJob(research_id=research.id).perform()

    # Make sure we got at least one research iteration
    iterations = await ResearchIteration.all()
    assert len(iterations) > 0

    # Ensure there are multiple ResearchQueryJobs
    query_jobs = background_jobs.all_completed_jobs_by_type(ResearchQueryJob)
    assert len(query_jobs) > 0

    # Ensure each ResearchQueryJob is for a different query
    query_data = [job.job_details["generated_query_data"] for job in query_jobs]
    assert len(query_data) == len(set(query_data))

    # Ensure the Research was completed
    await research.refresh_from_db()
    await research.fetch_related("iterations__queries")
    assert research.is_completed


@pytest.mark.asyncio
async def test_research_job_with_slack_source():
    user = await create_user()
    await user.fetch_related("organization")
    await user.add_integration(Integration.SLACK)
    await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.SLACK,
        access_token="xoxp-test-token",
        scope="channels:read,users:read,search:read",
    )

    # Content IDs are hardcoded to ensure the same content is used in the cassette request bodies
    first = await create_content(id="a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d", organization=user.organization)
    await first.indexer.index(
        SearchableData("Project update", "Team discussed project timeline", "https://example.com/update", "Alice"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    research = await Research.create(
        topic="What has the team discussed in Slack about project updates?",
        sources=[ResearchSource.INTERNAL, ResearchSource.SLACK],
        max_depth=1,
        max_breadth=3,
        creator_id=user.id,
        organization_id=user.organization_id,
    )

    async with JobsOutbox():
        await ResearchJob(research_id=research.id).perform()

    iterations = await ResearchIteration.all().prefetch_related("queries")
    assert len(iterations) > 0

    all_queries = [query for iteration in iterations for query in iteration.queries]
    slack_queries = [q for q in all_queries if q.source == ResearchSource.SLACK]

    assert len(slack_queries) > 0, "Expected at least one Slack query"
    assert all(q.source in (ResearchSource.INTERNAL, ResearchSource.SLACK) for q in all_queries)

    await research.refresh_from_db()
    await research.fetch_related("iterations__queries")
    assert research.is_completed


@pytest.mark.asyncio
async def test_research_continues_when_no_results_found():
    """When a search query returns no results, research should continue with alternative directions."""
    user = await create_user()
    await user.fetch_related("organization")

    research = await Research.create(
        topic="Information about quantum flux capacitors in our system",
        sources=[ResearchSource.INTERNAL],
        max_depth=2,
        max_breadth=1,
        creator_id=user.id,
        organization_id=user.organization_id,
    )

    async with JobsOutbox():
        await ResearchJob(research_id=research.id).perform()

    iterations = await ResearchIteration.all().prefetch_related("queries")

    assert len(iterations) >= 2, "Research should continue to next iteration even with no results"

    first_iteration = iterations[0]
    assert first_iteration.depth == 0
    assert len(first_iteration.queries) > 0
    assert all(query.is_completed for query in first_iteration.queries)
    assert all(len(query.learnings) == 0 for query in first_iteration.queries)

    second_iteration = iterations[1]
    assert second_iteration.depth == 1
    assert second_iteration.directions != first_iteration.directions
    assert len(second_iteration.queries) > 0
    assert all(query.is_completed for query in second_iteration.queries)

    await research.refresh_from_db()
    await research.fetch_related("iterations__queries")
    assert research.is_completed


@pytest.mark.asyncio
async def test_research_content_excluded_from_content_search():
    """Research-authored content is excluded from ContentResearchQuery but accessible via ContentLookupQuery."""
    user = await create_user()
    await user.fetch_related("organization")

    research_content = await create_content(organization=user.organization)
    await research_content.indexer.index(
        SearchableData(
            "Research Report on Fruits",
            "Detailed analysis of various fruits",
            "https://example.com/research-report",
            f"convictional <{settings.research_email_from}>",
        ),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.EMAIL_THREAD, Sharing.ORGANIZATION),
    )

    regular_content = await create_content(organization=user.organization)
    await regular_content.indexer.index(
        SearchableData(
            "Regular Report on Fruits",
            "Normal report about fruits",
            "https://example.com/regular-report",
            "user <user@example.com>",
        ),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.EMAIL_THREAD, Sharing.ORGANIZATION),
    )

    # ContentResearchQuery excludes research-authored content
    search_results = await ContentResearchQuery(organization=user.organization, query="fruits report").execute()
    assert regular_content in search_results
    assert research_content not in search_results

    # ContentLookupQuery includes research-authored content
    lookup_results = await ContentLookupQuery(organization=user.organization, query="Research Report").execute()
    assert any(result.id == research_content.id for result in lookup_results)


#
# Scheduled research jobs
#


@pytest.mark.asyncio
async def test_prepare_scheduled_research_sets_title_and_split():
    schedule = await create_scheduled_research(
        prompt="Summarize SaaS funding weekly as bullet points",
        topic_prompt=None,
        formatting_prompt=None,
    )

    await PrepareScheduledResearchJob(scheduled_research_id=schedule.id).perform()

    await schedule.refresh_from_db()
    assert not schedule.is_untitled
    assert schedule.topic_prompt is not None
    assert schedule.preparation_failed_at is None


@pytest.mark.asyncio
@freeze_time("2026-04-15 09:10:00", tz_offset=0)  # Wednesday, within the 9:00 Wed recurrence window
async def test_check_scheduled_research_enqueues_due_schedules_and_respects_idempotency():
    # Due this hour, never delivered → should enqueue
    fresh = await create_scheduled_research(schedule_cron="0 9 * * 3")
    # Due this hour, already delivered for THIS refresh window → should NOT enqueue (idempotency gate)
    already_delivered = await create_scheduled_research(
        schedule_cron="0 9 * * 3",
        last_delivered_at=datetime(2026, 4, 15, 9, 5, tzinfo=UTC),
    )
    # Regression: due this hour, last delivered on the PRIOR cycle (last Wednesday) → should still enqueue.
    # The original idempotency gate compared against the prior cron tick, which permanently filtered every
    # schedule after its first delivery and meant the recurring path never fired in production.
    delivered_prior_cycle = await create_scheduled_research(
        schedule_cron="0 9 * * 3",
        last_delivered_at=datetime(2026, 4, 8, 9, 5, tzinfo=UTC),
    )
    # Not due this hour (fires Thursday) → should NOT enqueue
    not_due = await create_scheduled_research(schedule_cron="0 9 * * 4")

    async with JobsOutbox() as outbox:
        await CheckScheduledResearchJob().perform()
        scheduled_ids = {
            j.job_definition.scheduled_research_id
            for j in outbox.jobs
            if j.job_type == ScheduledResearchJob.job_type()
        }

    assert fresh.id in scheduled_ids
    assert delivered_prior_cycle.id in scheduled_ids
    assert already_delivered.id not in scheduled_ids
    assert not_due.id not in scheduled_ids


@pytest.mark.asyncio
async def test_scheduled_research_job_creates_delivery_and_research():
    # Regression: publish must NOT be enqueued upfront. _check_research_completion reads the
    # delivery row and enqueues publish only after the research finishes — racing publish ahead
    # of the iteration/query tree shipped empty emails in production.
    schedule = await create_scheduled_research(topic_prompt="What happened last week")

    async with JobsOutbox() as outbox:
        await ScheduledResearchJob(scheduled_research_id=schedule.id).perform()

        research_jobs = [j for j in outbox.jobs if j.job_type == ResearchJob.job_type()]
        publish_jobs = [j for j in outbox.jobs if j.job_type == PublishScheduledResearchJob.job_type()]

        # Clear before the context-manager exit so the downstream cascade doesn't run.
        await JobsOutbox.reset()

    assert len(research_jobs) == 1
    assert publish_jobs == []

    delivery = await ScheduledResearchDelivery.get(scheduled_research_id=schedule.id)
    assert str(delivery.research_id) == research_jobs[0].job_details["research_id"]
    assert delivery.delivered_at is None


@pytest.mark.asyncio
@freeze_time("2026-04-15 09:10:00", tz_offset=0)  # Wednesday, within the 9:00 Wed recurrence window
async def test_scheduled_research_job_skips_when_already_delivered_for_window():
    # Heartbeat re-firing during an active recurrence window after delivery already happened:
    # the idempotency gate should short-circuit.
    schedule = await create_scheduled_research(schedule_cron="0 9 * * 3")
    schedule.last_delivered_at = datetime(2026, 4, 15, 9, 5, tzinfo=UTC)
    await schedule.save()

    async with JobsOutbox() as outbox:
        await ScheduledResearchJob(scheduled_research_id=schedule.id).perform()

        research_jobs = [j for j in outbox.jobs if j.job_type == ResearchJob.job_type()]
        assert research_jobs == []


@pytest.mark.asyncio
@freeze_time("2026-04-15 09:10:00", tz_offset=0)  # Wednesday, within the 9:00 Wed recurrence window
async def test_scheduled_research_job_runs_when_last_delivery_was_prior_cycle():
    # Regression: a schedule delivered on the previous cron tick must still fire on the current one.
    # The prior gate compared against the cron tick before the current fire, so any schedule that had ever
    # delivered would silently no-op forever on the recurring path.
    schedule = await create_scheduled_research(schedule_cron="0 9 * * 3")
    schedule.last_delivered_at = datetime(2026, 4, 8, 9, 5, tzinfo=UTC)
    await schedule.save()

    async with JobsOutbox() as outbox:
        await ScheduledResearchJob(scheduled_research_id=schedule.id).perform()

        research_jobs = [j for j in outbox.jobs if j.job_type == ResearchJob.job_type()]
        await JobsOutbox.reset()

    assert len(research_jobs) == 1


@pytest.mark.asyncio
async def test_scheduled_research_job_force_bypasses_idempotency_gate():
    # Explicit user action (run_now) must still run even after the scheduled fire delivered today.
    schedule = await create_scheduled_research(schedule_cron="0 9 * * 3")
    schedule.last_delivered_at = datetime.now(UTC)
    await schedule.save()

    async with JobsOutbox() as outbox:
        await ScheduledResearchJob(scheduled_research_id=schedule.id, force=True).perform()

        research_jobs = [j for j in outbox.jobs if j.job_type == ResearchJob.job_type()]
        assert len(research_jobs) == 1
        await JobsOutbox.reset()


# _check_research_completion ignores generated_query_data; this is a placeholder that satisfies the model.
_PLACEHOLDER_QUERY_JSON = GeneratedResearchQuery(title="x", terms="x", goals="x").model_dump_json()


async def _setup_scheduled_research_with_queries(*, complete_all_queries: bool):
    # max_depth=1 keeps depth-0 queries out of is_within_depth — the helper doesn't spawn child
    # iterations, so this avoids exercising the "should-have-spawned-but-didn't" gap in is_completed.
    schedule = await create_scheduled_research(topic_prompt="Kinds and colours of fruits")
    research = await Research.create(
        topic="Kinds and colours of fruits",
        sources=[ResearchSource.INTERNAL],
        max_depth=1,
        creator_id=schedule.creator_id,
        organization_id=schedule.organization_id,
    )
    iteration = await ResearchIteration.create(
        research=research,
        title="Fruit colours",
        directions=research.topic,
        queries_count=2,
        depth=0,
    )
    first_query = await ResearchQuery.create(
        title="Apple colour", goals="Apples", research=research, iteration=iteration, source=ResearchSource.INTERNAL
    )
    second_query = await ResearchQuery.create(
        title="Banana colour", goals="Bananas", research=research, iteration=iteration, source=ResearchSource.INTERNAL
    )
    await first_query.mark_completed(learnings=["Apples are red"])
    if complete_all_queries:
        await second_query.mark_completed(learnings=["Bananas are yellow"])

    await ScheduledResearchDelivery.create(scheduled_research_id=schedule.id, research_id=research.id)
    return schedule, research, iteration


@pytest.mark.asyncio
async def test_check_research_completion_enqueues_publish_for_scheduled_research():
    schedule, _, iteration = await _setup_scheduled_research_with_queries(complete_all_queries=True)

    async with JobsOutbox() as outbox:
        query_job = ResearchQueryJob(iteration_id=iteration.id, generated_query_data=_PLACEHOLDER_QUERY_JSON)
        await query_job._check_research_completion(iteration)

        publish_jobs = [j for j in outbox.jobs if j.job_type == PublishScheduledResearchJob.job_type()]
        await JobsOutbox.reset()

    assert len(publish_jobs) == 1
    assert publish_jobs[0].job_details["scheduled_research_id"] == str(schedule.id)


@pytest.mark.asyncio
async def test_check_research_completion_does_not_enqueue_publish_when_queries_incomplete():
    _, _, iteration = await _setup_scheduled_research_with_queries(complete_all_queries=False)

    async with JobsOutbox() as outbox:
        query_job = ResearchQueryJob(iteration_id=iteration.id, generated_query_data=_PLACEHOLDER_QUERY_JSON)
        await query_job._check_research_completion(iteration)

        publish_jobs = [j for j in outbox.jobs if j.job_type == PublishScheduledResearchJob.job_type()]
        await JobsOutbox.reset()

    assert publish_jobs == []


@pytest.mark.asyncio
async def test_publish_scheduled_research_email_includes_findings_and_sources(vcr):
    # End-to-end check that the publish prompt has both <learnings> and <sources>, and the rendered
    # email includes a real source citation rather than the system prompt's "No relevant content was
    # found" fallback. VCR matches on URL/method only, so a regression in the prompt would still get
    # the cached response replayed — to plug that hole we also assert the captured request body had
    # the <sources> block.
    fake_delivery.reset()

    user = await create_user()
    await user.fetch_related("organization")

    # Hardcoded IDs keep the recorded cassette stable across runs.
    apples = await create_content(id="20b1d2d7-f11f-48d5-a709-a24dd8e728b1", organization=user.organization)
    await apples.indexer.index(
        SearchableData("Apples", "Apples are a red fruit", "https://example.com/apples", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )
    bananas = await create_content(id="65fe6aa2-f247-41b3-9f61-b512f5e398c6", organization=user.organization)
    await bananas.indexer.index(
        SearchableData("Bananas", "Bananas are a yellow fruit", "https://example.com/bananas", "Bob Clams"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    schedule = await create_scheduled_research(
        creator_id=user.id,
        organization_id=user.organization_id,
        topic_prompt="Kinds and colours of fruits",
        formatting_prompt="bullets",
        title="Fruit roundup",
    )
    research = await Research.create(
        topic="Kinds and colours of fruits",
        sources=[ResearchSource.INTERNAL],
        creator_id=schedule.creator_id,
        organization_id=schedule.organization_id,
    )

    # Stand in for what the upstream chain (ResearchJob → ResearchIterationJob → ResearchQueryJob)
    # produces: a completed iteration + query carrying both learnings and the underlying content_result_ids.
    iteration = await ResearchIteration.create(
        research=research, title="Fruit colours", directions=research.topic, queries_count=1, depth=0
    )
    query = await ResearchQuery.create(
        title="What colours are different fruits",
        goals="Identify fruit colours",
        research=research,
        iteration=iteration,
        source=ResearchSource.INTERNAL,
        content_result_ids=[apples.id, bananas.id],
    )
    await query.mark_completed(learnings=["Apples are red", "Bananas are yellow"])

    delivery = await ScheduledResearchDelivery.create(scheduled_research_id=schedule.id, research_id=research.id)

    await PublishScheduledResearchJob(scheduled_research_id=schedule.id, research_id=research.id).perform()

    await schedule.refresh_from_db()
    assert schedule.last_delivered_at is not None

    await delivery.refresh_from_db()
    assert delivery.delivered_at is not None

    sent = fake_delivery.by_recipient(user.email)
    assert len(sent) == 1
    assert "Fruit roundup" in sent[0].subject

    body = sent[0].text
    assert "No relevant content was found" not in body
    # The citation filter rewrites [^content:UUID] markers into source-URL links — its presence
    # in the rendered body proves the LLM was given (and used) real source content.
    assert "example.com/apples" in body or "example.com/bananas" in body

    # VCR matches on URL/method only, so the cassette would replay the recorded "good" response even
    # if the prompt regressed. Inspect the captured request body directly to pin down that the LLM
    # was actually sent the <sources> block alongside the learnings — and that each source is
    # identified by its short S-token, never the raw Content UUID (the model must never see a UUID).
    [anthropic_request] = [r for r in vcr.requests if "api.anthropic.com" in r.uri]
    request_body = anthropic_request.body.decode()
    assert "<sources>" in request_body
    assert "<id>S1</id>" in request_body
    assert "<id>S2</id>" in request_body
    assert str(apples.id) not in request_body
    assert str(bananas.id) not in request_body
    assert "[^content:" not in request_body


@pytest.mark.asyncio
async def test_research_question_complete_job_no_ops_when_already_completed():
    # Duplicate completion jobs can be enqueued for one run. An already-complete question must no-op
    # rather than re-run the LLM and enqueue a second email.
    research = await create_research()
    question = await create_research_question(creator_id=research.creator_id, research_id=research.id)
    await question.mark_completed(response="Original findings.")

    async with JobsOutbox() as outbox:
        await ResearchQuestionCompleteJob(research_question_id=question.id).perform()
        send_jobs = [j for j in outbox.jobs if j.job_type == SendResearchQuestionEmailJob.job_type()]
        await JobsOutbox.reset()

    assert send_jobs == []
    await question.refresh_from_db()
    assert question.response == "Original findings."


@pytest.mark.asyncio
async def test_concurrent_research_question_complete_jobs_send_one_email():
    # Two completion jobs racing to finish must still yield one email: both clear the fast path and
    # enter perform(), where the select_for_update re-check lets only the first write and send.
    user = await create_user()
    await user.fetch_related("organization")
    research = await Research.create(
        topic="Kinds and colours of fruits",
        sources=[ResearchSource.INTERNAL],
        creator_id=user.id,
        organization_id=user.organization_id,
    )
    iteration = await ResearchIteration.create(
        research=research, title="Fruit", directions=research.topic, queries_count=1, depth=0
    )
    query = await ResearchQuery.create(
        title="Apple colour", goals="Apples", research=research, iteration=iteration, source=ResearchSource.INTERNAL
    )
    await query.mark_completed(learnings=["Apples are red"])
    question = await create_research_question(creator_id=user.id, research_id=research.id)

    async with JobsOutbox() as outbox:
        await asyncio.gather(
            ResearchQuestionCompleteJob(research_question_id=question.id).perform(),
            ResearchQuestionCompleteJob(research_question_id=question.id).perform(),
        )
        send_jobs = [j for j in outbox.jobs if j.job_type == SendResearchQuestionEmailJob.job_type()]
        await JobsOutbox.reset()

    assert len(send_jobs) == 1
    await question.refresh_from_db()
    assert question.is_response_complete


@pytest.mark.asyncio
async def test_research_report_email_strips_and_records_unknown_citations(monkeypatch):
    fake_delivery.reset()

    user = await create_user()
    await user.fetch_related("organization")

    # Resolvable source — an external URL renders as a real citation link in the body.
    real = await create_content(source_url="https://example.com/real", organization=user.organization)

    research = await create_research(creator_id=user.id, organization_id=user.organization_id)
    iteration = await ResearchIteration.create(
        research=research, title="Findings", directions=research.topic, queries_count=1, depth=0
    )
    query = await ResearchQuery.create(
        title="What is real",
        goals="Find real content",
        research=research,
        iteration=iteration,
        source=ResearchSource.INTERNAL,
        content_result_ids=[real.id],
    )
    await query.mark_completed(learnings=["Real learning"])

    fabricated = "33333333-3333-3333-3333-333333333333"
    question = await create_research_question(creator_id=user.id, research_id=research.id)
    await question.mark_completed(response=f"Real source [^content:{real.id}] and fabricated [^content:{fabricated}].")

    # A valid DSN lets the mailer's guard pass; recorders capture the Sentry calls the mailer makes.
    monkeypatch.setattr(settings, "sentry_dsn", "https://example@sentry.io/1")
    captured_messages: list[tuple] = []
    captured_contexts: list[tuple] = []
    captured_tags: list[tuple] = []
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda *a, **k: captured_messages.append((a, k)))
    monkeypatch.setattr(sentry_sdk.Scope, "set_context", lambda self, *a, **k: captured_contexts.append((a, k)))
    monkeypatch.setattr(sentry_sdk.Scope, "set_tag", lambda self, *a, **k: captured_tags.append((a, k)))

    # The mailer reads creator.email, research.iterations→queries, and the in-memory response.
    prefetched_question = (
        await ResearchQuestion.filter(id=question.id)
        .prefetch_related("research__iterations__queries", "creator__organization")
        .first()
    )
    assert prefetched_question is not None
    await ResearchQuestionMailer(research_question=prefetched_question).send()

    sent = fake_delivery.by_recipient(user.email)
    assert len(sent) == 1
    body = sent[0].text
    # Real citation renders as a link; the fabricated marker is stripped and no raw markers survive.
    assert "example.com/real" in body
    assert f"[^content:{fabricated}]" not in body
    assert "[^content:" not in body

    # Exactly one Sentry warning with the stable message and warning level.
    assert len(captured_messages) == 1
    message_args, message_kwargs = captured_messages[0]
    assert message_args[0] == "Research response cited unknown content ids"
    assert message_kwargs["level"] == "warning"

    contexts = {args[0]: args[1] for args, _ in captured_contexts}
    payload = contexts["Research Citations"]
    assert payload["unresolved_content_ids"] == [fabricated]
    assert payload["unresolved_count"] == 1
    assert payload["total_citation_count"] == 2
    assert payload["organization_id"] == str(user.organization_id)
    assert payload["research_id"] == str(research.id)
    assert payload["research_question_id"] == str(prefetched_question.id)

    # The fabricated id has no Content row and never appeared in a learning → a synthesis-step hallucination.
    assert payload["hallucinated_count"] == 1
    assert payload["foreign_content_count"] == 0
    assert payload["cross_org_count"] == 0
    assert payload["citation_origin"] == "synthesis"
    assert payload["from_synthesis_count"] == 1
    assert payload["from_extraction_count"] == 0
    assert payload["result_set_size"] == 1

    tags = {args[0]: args[1] for args, _ in captured_tags}
    assert tags["research.citation_origin"] == "synthesis"
    assert tags["research.unresolved_kind"] == "hallucinated"
    assert tags["research.has_cross_org"] is False
    assert tags["research.llm_model"] == DEFAULT_MODEL

    # Negative case: only a resolvable citation → nothing stripped and no Sentry warning.
    fake_delivery.reset()
    captured_messages.clear()
    captured_contexts.clear()
    captured_tags.clear()
    # response is a protected column; the mailer reads the in-memory attribute, so mutate without saving.
    prefetched_question.response = f"Only real [^content:{real.id}]."
    await ResearchQuestionMailer(research_question=prefetched_question).send()

    resent = fake_delivery.by_recipient(user.email)
    assert len(resent) == 1
    assert "example.com/real" in resent[0].text
    assert len(captured_messages) == 0


@pytest.mark.asyncio
async def test_scheduled_research_email_strips_and_records_unknown_citations(monkeypatch):
    fake_delivery.reset()

    user = await create_user()
    await user.fetch_related("organization")

    real = await create_content(source_url="https://example.com/real", organization=user.organization)

    scheduled_research = await create_scheduled_research(creator_id=user.id, organization_id=user.organization_id)
    research = await create_research(creator_id=user.id, organization_id=user.organization_id)
    iteration = await ResearchIteration.create(
        research=research, title="Findings", directions=research.topic, queries_count=1, depth=0
    )
    await ResearchQuery.create(
        title="What is real",
        goals="Find real content",
        research=research,
        iteration=iteration,
        source=ResearchSource.INTERNAL,
        content_result_ids=[real.id],
    )

    monkeypatch.setattr(settings, "sentry_dsn", "https://example@sentry.io/1")
    captured_messages: list[tuple] = []
    captured_contexts: list[tuple] = []
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda *a, **k: captured_messages.append((a, k)))
    monkeypatch.setattr(sentry_sdk.Scope, "set_context", lambda self, *a, **k: captured_contexts.append((a, k)))

    # _build_message reads creator.email and research.iterations→queries (sync relational access).
    await research.fetch_related("iterations__queries")
    await scheduled_research.fetch_related("creator")

    fabricated = "44444444-4444-4444-4444-444444444444"
    rendered_markdown = f"Real [^content:{real.id}] and fabricated [^content:{fabricated}]."
    mailer = ScheduledResearchMailer(
        scheduled_research=scheduled_research, research=research, rendered_markdown=rendered_markdown
    )
    await mailer.send()

    sent = fake_delivery.by_recipient(user.email)
    assert len(sent) == 1
    body = sent[0].text
    assert "example.com/real" in body
    assert "[^content:" not in body

    assert len(captured_messages) == 1
    message_args, message_kwargs = captured_messages[0]
    assert message_args[0] == "Research response cited unknown content ids"
    assert message_kwargs["level"] == "warning"

    contexts = {args[0]: args[1] for args, _ in captured_contexts}
    payload = contexts["Research Citations"]
    assert payload["unresolved_content_ids"] == [fabricated]
    assert payload["research_question_id"] is None
    assert payload["organization_id"] == str(user.organization_id)
    assert payload["research_id"] == str(research.id)


@pytest.mark.asyncio
async def test_research_citation_classification_and_origin(monkeypatch):
    fake_delivery.reset()

    user = await create_user()
    await user.fetch_related("organization")
    other_user = await create_user()
    await other_user.fetch_related("organization")

    # Three shapes of unresolvable citation: a same-org row left out of the run's results, a row
    # owned by another org (a cross-tenant leak), and a fabricated id with no row at all.
    real = await create_content(source_url="https://example.com/real", organization=user.organization)
    orphan = await create_content(source_url="https://example.com/orphan", organization=user.organization)
    foreign = await create_content(source_url="https://example.com/foreign", organization=other_user.organization)

    research = await create_research(creator_id=user.id, organization_id=user.organization_id)
    iteration = await ResearchIteration.create(
        research=research, title="Findings", directions=research.topic, queries_count=1, depth=0
    )
    query = await ResearchQuery.create(
        title="What is real",
        goals="Find real content",
        research=research,
        iteration=iteration,
        source=ResearchSource.INTERNAL,
        content_result_ids=[real.id],
    )
    # The orphan id is cited inside a learning, so it entered at the extraction step.
    await query.mark_completed(learnings=[f"Orphan finding [^content:{orphan.id}]"])

    fabricated = "55555555-5555-5555-5555-555555555555"
    question = await create_research_question(creator_id=user.id, research_id=research.id)
    await question.mark_completed(
        response=(
            f"Real [^content:{real.id}], orphan [^content:{orphan.id}], "
            f"foreign [^content:{foreign.id}], fake [^content:{fabricated}]."
        )
    )

    monkeypatch.setattr(settings, "sentry_dsn", "https://example@sentry.io/1")
    captured_contexts: list[tuple] = []
    captured_tags: list[tuple] = []
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda *a, **k: None)
    monkeypatch.setattr(sentry_sdk.Scope, "set_context", lambda self, *a, **k: captured_contexts.append((a, k)))
    monkeypatch.setattr(sentry_sdk.Scope, "set_tag", lambda self, *a, **k: captured_tags.append((a, k)))

    prefetched_question = (
        await ResearchQuestion.filter(id=question.id)
        .prefetch_related("research__iterations__queries", "creator__organization")
        .first()
    )
    assert prefetched_question is not None
    await ResearchQuestionMailer(research_question=prefetched_question).send()

    payload = {args[0]: args[1] for args, _ in captured_contexts}["Research Citations"]
    # One of each class, in first-appearance order (the resolvable real id is excluded).
    assert payload["unresolved_content_ids"] == [str(orphan.id), str(foreign.id), fabricated]
    assert payload["hallucinated_count"] == 1
    assert payload["foreign_content_count"] == 1
    assert payload["cross_org_count"] == 1
    assert sum(payload["content_type_breakdown"].values()) == 2

    # Orphan came from a learning (extraction); foreign + fabricated appear only in the report (synthesis).
    assert payload["citation_origin"] == "mixed"
    assert payload["from_extraction_count"] == 1
    assert payload["from_synthesis_count"] == 2

    tags = {args[0]: args[1] for args, _ in captured_tags}
    # A cross-org leak dominates the kind tag and raises the dedicated flag.
    assert tags["research.unresolved_kind"] == "cross_org"
    assert tags["research.has_cross_org"] is True
    assert tags["research.citation_origin"] == "mixed"
    assert tags["research.llm_model"] == DEFAULT_MODEL
