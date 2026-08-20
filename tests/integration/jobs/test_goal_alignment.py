from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.goal_alignment import CONTENT_BATCH_SIZE, ScoreGoalAlignmentJob
from app.models.workspaces.goals import Goal, GoalAlignment
from config.enums import ContentType, Sharing
from infra.jobs import InlineJobs, JobsOutbox
from infra.vectors import EMBEDDING_DIMENSION
from tests.helpers.factories import create_content, create_goal, create_organization, create_user

pytestmark = pytest.mark.real_embeddings


def _make_embedding(seed: int = 0, base: list[float] | None = None) -> list[float]:
    """Build a unit-ish embedding for testing cosine similarity thresholds."""
    vec = [0.0] * EMBEDDING_DIMENSION
    if base:
        vec = list(base)
    vec[seed % EMBEDDING_DIMENSION] += 1.0
    return vec


GOAL_EMBEDDING = _make_embedding(0)
ALIGNED_EMBEDDING = _make_embedding(0, base=_make_embedding(1))


async def create_goal_content(goal: Goal, organization):
    return await create_content(
        organization=organization,
        organization_id=organization.id,
        source_id=str(goal.global_id),
        content_type=ContentType.GOAL,
        sharing=Sharing.ORGANIZATION,
        title=goal.title,
        index_content=goal.description,
        embedding=GOAL_EMBEDDING,
    )


@pytest.mark.asyncio
async def test_scoring_creates_alignment_records():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    goal = await create_goal(
        organization_id=organization.id,
        creator_id=user.id,
        title="Increase revenue by 20%",
        description="Grow annual recurring revenue by 20% through new customer acquisition and upselling.",
    )
    await create_goal_content(goal, organization)
    content = await create_content(
        organization=organization,
        organization_id=organization.id,
        sharing=Sharing.ORGANIZATION,
        content_type=ContentType.MEETING,
        title="Q1 Sales Pipeline Review",
        index_content="Discussed strategies to close three enterprise deals worth $500K total. "
        "The team agreed to focus on upselling existing accounts and expanding into new verticals.",
        embedding=ALIGNED_EMBEDDING,
    )
    await create_content(
        organization=organization,
        organization_id=organization.id,
        sharing=Sharing.PRIVATE,
        content_type=ContentType.POST,
        title="My private notes on revenue",
        index_content="Private notes about our revenue strategy and targets.",
        embedding=ALIGNED_EMBEDDING,
    )

    job = ScoreGoalAlignmentJob(organization_id=organization.id)
    await job.perform()

    alignments = await GoalAlignment.filter(organization_id=organization.id).all()
    assert len(alignments) == 1
    alignment = alignments[0]
    assert alignment.content_id == content.id
    assert alignment.goal_id == goal.id
    assert alignment.signal is not None
    assert 0.0 <= alignment.alignment_score <= 1.0
    assert alignment.description


@pytest.mark.asyncio
async def test_content_can_align_to_multiple_goals():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    goal1 = await create_goal(
        organization_id=organization.id,
        creator_id=user.id,
        title="Increase revenue by 20%",
        description="Grow annual recurring revenue by 20% through new customer acquisition and upselling.",
    )
    await create_goal_content(goal1, organization)
    goal2 = await create_goal(
        organization_id=organization.id,
        creator_id=user.id,
        title="Expand into enterprise market",
        description="Close 10 enterprise deals worth over $100K each this year.",
    )
    await create_goal_content(goal2, organization)
    await create_content(
        organization=organization,
        organization_id=organization.id,
        sharing=Sharing.ORGANIZATION,
        content_type=ContentType.MEETING,
        title="Enterprise Sales Strategy",
        index_content="Reviewed our enterprise pipeline targeting Fortune 500 companies. "
        "Three deals worth $200K each are progressing well. This will significantly boost our ARR.",
        embedding=ALIGNED_EMBEDDING,
    )

    job = ScoreGoalAlignmentJob(organization_id=organization.id)
    await job.perform()

    alignments = await GoalAlignment.filter(organization_id=organization.id).all()
    assert len(alignments) == 2


# Goals are scored concurrently in nondeterministic order, but this test's two goals
# get genuinely different judgments (one aligned, one not). Match cassettes on the
# request body so each goal's request resolves to its own response regardless of the
# order the concurrent calls fire, rather than VCR's default URL-only ordered replay.
@pytest.mark.vcr(match_on=["method", "scheme", "host", "port", "path", "query", "body"])
@pytest.mark.asyncio
async def test_stale_alignments_for_closed_goals_are_cleaned_up():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    goal_to_close = await create_goal(
        organization_id=organization.id,
        creator_id=user.id,
        title="Increase revenue by 20%",
        description="Grow annual recurring revenue by 20% through new customer acquisition and upselling.",
    )
    await create_goal_content(goal_to_close, organization)
    goal_retention = await create_goal(
        organization_id=organization.id,
        creator_id=user.id,
        title="Improve employee retention",
        description="Reduce employee turnover to below 10% annually.",
    )
    await create_goal_content(goal_retention, organization)
    await create_content(
        organization=organization,
        organization_id=organization.id,
        sharing=Sharing.ORGANIZATION,
        content_type=ContentType.MEETING,
        title="Q1 Sales Pipeline Review",
        index_content="Discussed strategies to close three enterprise deals worth $500K total.",
        embedding=ALIGNED_EMBEDDING,
    )

    job = ScoreGoalAlignmentJob(organization_id=organization.id)
    await job.perform()

    closed_goal_alignments = await GoalAlignment.filter(goal_id=goal_to_close.id).count()
    assert closed_goal_alignments > 0

    await goal_to_close.close()

    job2 = ScoreGoalAlignmentJob(organization_id=organization.id)
    await job2.perform()

    assert await GoalAlignment.filter(goal_id=goal_to_close.id).count() == 0


@pytest.mark.asyncio
async def test_batch_self_enqueues_next_batch(background_jobs: InlineJobs):
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    goal = await create_goal(
        organization_id=organization.id,
        creator_id=user.id,
        title="Increase revenue by 20%",
        description="Grow annual recurring revenue by 20% through new customer acquisition and upselling.",
    )
    await create_goal_content(goal, organization)
    await create_content(
        organization=organization,
        organization_id=organization.id,
        sharing=Sharing.ORGANIZATION,
        content_type=ContentType.MEETING,
        title="Q1 Sales Pipeline Review",
        index_content="Discussed strategies to close three enterprise deals worth $500K total.",
        embedding=ALIGNED_EMBEDDING,
    )

    async with JobsOutbox():
        job = ScoreGoalAlignmentJob(organization_id=organization.id)
        await job.perform()

    completed_jobs = background_jobs.all_completed_jobs_by_type(ScoreGoalAlignmentJob)
    assert len(completed_jobs) == 1

    next_job = completed_jobs[0]
    assert next_job.job_details["offset"] == CONTENT_BATCH_SIZE
    assert next_job.job_details["organization_id"] == str(organization.id)


@pytest.mark.asyncio
async def test_goal_without_index_content_is_excluded():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    goal = await create_goal(
        organization_id=organization.id,
        creator_id=user.id,
        title="Increase revenue by 20%",
        description="Grow annual recurring revenue by 20%.",
    )
    await create_content(
        organization=organization,
        organization_id=organization.id,
        source_id=str(goal.global_id),
        content_type=ContentType.GOAL,
        sharing=Sharing.ORGANIZATION,
        title=goal.title,
        index_content="",
        embedding=GOAL_EMBEDDING,
    )
    await create_content(
        organization=organization,
        organization_id=organization.id,
        sharing=Sharing.ORGANIZATION,
        content_type=ContentType.MEETING,
        title="Q1 Sales Pipeline Review",
        index_content="Discussed strategies to close three enterprise deals worth $500K total.",
        embedding=ALIGNED_EMBEDDING,
    )

    job = ScoreGoalAlignmentJob(organization_id=organization.id)
    await job.perform()

    alignments = await GoalAlignment.filter(organization_id=organization.id).all()
    assert len(alignments) == 0


@pytest.mark.asyncio
async def test_content_indexed_before_goal_activation_is_excluded():
    organization = await create_organization()
    user = await create_user(organization_id=organization.id)
    activated_at = datetime.now(UTC)
    goal = await create_goal(
        organization_id=organization.id,
        creator_id=user.id,
        title="Increase revenue by 20%",
        description="Grow annual recurring revenue by 20%.",
        activated_at=activated_at,
    )
    await create_goal_content(goal, organization)
    await create_content(
        organization=organization,
        organization_id=organization.id,
        sharing=Sharing.ORGANIZATION,
        content_type=ContentType.MEETING,
        title="Q1 Sales Pipeline Review",
        index_content="Discussed strategies to close three enterprise deals worth $500K total.",
        embedding=ALIGNED_EMBEDDING,
        last_indexed_at=activated_at - timedelta(days=1),
    )

    job = ScoreGoalAlignmentJob(organization_id=organization.id)
    await job.perform()

    alignments = await GoalAlignment.filter(organization_id=organization.id).all()
    assert len(alignments) == 0
