import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import sentry_sdk
from pydantic import BaseModel, Field
from sentry_sdk.ai.monitoring import ai_track
from tortoise.expressions import Q

from app.models.accounts import Organization
from app.models.collaboration.content import Content
from app.models.workspaces.goals import Goal, GoalAlignment
from app.prompts.engine import build_prompt
from config.enums import ContentType, JobQueue, Sharing, SignalStrength
from infra.db import allow_soft_deleted, transaction
from infra.jobs import JobDefinition, enqueue_job
from infra.vectors import cosine_similarity

ALIGNMENT_MODEL = "claude-haiku-4-5"
CONTENT_BATCH_SIZE = 100
MAX_CONCURRENT_LLM_REQUESTS = 20
MAX_FEW_SHOT_EXAMPLES = 3
MIN_ALIGNMENT_SCORE = 0.5

SCORABLE_CONTENT_TYPES = (ContentType.POST, ContentType.MEETING)


@dataclass
class FewShotExample:
    content_type: str
    content_title: str
    content_body: str
    is_aligned: bool
    signal: str | None = None
    description: str | None = None


@dataclass
class GoalScoringContext:
    goals: list[Goal]
    embeddings: dict[UUID, list[float]]
    goal_content: dict[UUID, str]
    examples: dict[UUID, list[FewShotExample]]


class AlignmentJudgment(BaseModel):
    is_aligned: bool = Field(description="Whether the content is meaningfully aligned with the goal")
    signal: SignalStrength | None = Field(
        None,
        description="The strength of the alignment signal: strong, medium, or weak. Only set if is_aligned is true.",
    )
    alignment_score: float = Field(
        ge=0.0, le=1.0, description="How aligned is the content with the goal from 0.0 to 1.0"
    )
    description: str | None = Field(
        None,
        description="A concise 1-2 sentence explanation of how the content relates to the goal. "
        "Only set if is_aligned is true.",
    )


class ScoreGoalAlignmentJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    organization_id: UUID
    offset: int = 0
    scored_since: datetime | None = None

    @ai_track("ScoreGoalAlignmentJob.perform")
    async def perform(self):
        organization = await Organization.get_or_none(id=self.organization_id)
        if not organization:
            return

        goals = await Goal.filter(Goal.filters.by_active_open_top_level(organization.id)).all()
        if not goals:
            return

        scored_since = await self._resolve_scored_since(organization.id)
        if self.offset == 0:
            await self._cleanup_stale_alignments(organization.id, goals)

        content_items = await self._fetch_content_batch(organization.id, scored_since)
        if not content_items:
            return

        context = await self._build_scoring_context(goals)
        actioned_pairs = await self._fetch_actioned_pairs(content_items)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_REQUESTS)
        scoring_tasks = [
            self._score_content(organization, content, context, actioned_pairs, semaphore) for content in content_items
        ]
        await asyncio.gather(*scoring_tasks)

        await enqueue_job(
            ScoreGoalAlignmentJob(
                organization_id=self.organization_id,
                offset=self.offset + CONTENT_BATCH_SIZE,
                scored_since=scored_since,
                unique=True,
            )
        )

    async def _resolve_scored_since(self, organization_id: UUID) -> datetime | None:
        if self.offset > 0:
            return self.scored_since

        last_alignment = await GoalAlignment.filter(organization_id=organization_id).order_by("-created_at").first()
        return last_alignment.created_at if last_alignment else None

    async def _cleanup_stale_alignments(self, organization_id: UUID, goals: list[Goal]):
        active_goal_ids = [goal.id for goal in goals]
        await GoalAlignment.filter(
            GoalAlignment.filters.stale_for_organization(organization_id, active_goal_ids)
        ).delete()

    async def _build_scoring_context(self, goals: list[Goal]) -> GoalScoringContext:
        embeddings, goal_content = await self._fetch_goal_content(goals)

        example_tasks = [self._fetch_examples_for_goal(goal.id) for goal in goals]
        results = await asyncio.gather(*example_tasks)
        examples = {goal.id: ex for goal, ex in zip(goals, results)}

        return GoalScoringContext(goals=goals, embeddings=embeddings, goal_content=goal_content, examples=examples)

    async def _fetch_content_batch(self, organization_id: UUID, scored_since: datetime | None) -> list[Content]:
        query = Content.filter(
            organization_id=organization_id,
            sharing=Sharing.ORGANIZATION,
            content_type__in=SCORABLE_CONTENT_TYPES,
            embedding__isnull=False,
            is_ai_excluded=False,
        ).order_by("id")
        if scored_since:
            query = query.filter(updated_at__gt=scored_since)
        return await query.offset(self.offset).limit(CONTENT_BATCH_SIZE).all()

    async def _fetch_goal_content(self, goals: list[Goal]) -> tuple[dict[UUID, list[float]], dict[UUID, str]]:
        goal_source_ids = {str(goal.global_id): goal.id for goal in goals}
        goal_content = await Content.filter(
            Content.filters.by_source_id_in(list(goal_source_ids.keys())),
            embedding__isnull=False,
        ).all()
        embeddings = {}
        index_content = {}
        for c in goal_content:
            goal_id = goal_source_ids[c.source_id]
            if not c.index_content:
                continue
            embeddings[goal_id] = c.embedding
            index_content[goal_id] = c.index_content
        return embeddings, index_content

    async def _fetch_examples_for_goal(self, goal_id: UUID) -> list[FewShotExample]:
        pinned = (
            await GoalAlignment.filter(
                goal_id=goal_id,
                pinned_by_id__isnull=False,
            )
            .prefetch_related("content")
            .order_by("-updated_at")
            .limit(MAX_FEW_SHOT_EXAMPLES)
        )

        async with allow_soft_deleted():
            rejected = (
                await GoalAlignment.filter(
                    goal_id=goal_id,
                    deleted_at__isnull=False,
                )
                .prefetch_related("content")
                .order_by("-updated_at")
                .limit(MAX_FEW_SHOT_EXAMPLES)
            )

        examples = [self._example_from_alignment(a, is_aligned=True) for a in pinned]
        examples += [self._example_from_alignment(a, is_aligned=False) for a in rejected]
        return examples

    def _example_from_alignment(self, alignment: GoalAlignment, *, is_aligned: bool) -> FewShotExample:
        return FewShotExample(
            content_type=alignment.content.content_type.value,
            content_title=alignment.content.title,
            content_body=(alignment.content.preview_content or alignment.content.index_content)[:500],
            is_aligned=is_aligned,
            signal=alignment.signal.value if is_aligned else None,
            description=alignment.description if is_aligned else None,
        )

    async def _fetch_actioned_pairs(self, content_items: list[Content]) -> set[tuple[UUID, UUID, datetime]]:
        content_ids = [c.id for c in content_items]
        async with allow_soft_deleted():
            rows = (
                await GoalAlignment.filter(
                    content_id__in=content_ids,
                )
                .filter(GoalAlignment.filters.actioned)
                .values_list("content_id", "goal_id", "content_indexed_at")
            )
        return {(content_id, goal_id, content_indexed_at) for content_id, goal_id, content_indexed_at in rows}

    async def _score_content(
        self,
        organization: Organization,
        content: Content,
        context: GoalScoringContext,
        actioned_pairs: set[tuple[UUID, UUID, datetime]],
        semaphore: asyncio.Semaphore,
    ):
        user_actioned_goal_ids = {
            goal_id
            for content_id, goal_id, content_indexed_at in actioned_pairs
            if content_id == content.id and content_indexed_at == content.last_indexed_at
        }

        scorable_goals = self._goals_to_score(content, context, user_actioned_goal_ids)
        scored_goals = []
        tasks = []
        for goal in scorable_goals:
            similarity = cosine_similarity(content.embedding, context.embeddings[goal.id])
            scored_goals.append(goal)
            goal_context = context.goal_content[goal.id]
            examples = context.examples.get(goal.id, [])
            tasks.append(self._score_pair(organization, content, goal, similarity, goal_context, examples, semaphore))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        succeeded_goal_ids: set[UUID] = set()
        alignments = []
        for goal, result in zip(scored_goals, results):
            if isinstance(result, BaseException):
                sentry_sdk.capture_exception(result)
                continue
            succeeded_goal_ids.add(goal.id)
            if result:
                alignments.append(result)

        await self._persist_alignments(content.id, content.last_indexed_at, succeeded_goal_ids, alignments)

    def _goals_to_score(
        self,
        content: Content,
        context: GoalScoringContext,
        user_actioned_goal_ids: set[UUID],
    ) -> list[Goal]:
        scorable = []
        for goal in context.goals:
            # Exclude content that pre-dates the goal activation to avoid scoring
            # old content unlikely to be relevant. This also excludes content that
            # led to goal creation — may revisit with better heuristics.
            if goal.activated_at and content.last_indexed_at and content.last_indexed_at < goal.activated_at:
                continue
            if goal.id in user_actioned_goal_ids:
                continue
            if goal.id not in context.embeddings:
                continue
            scorable.append(goal)
        return scorable

    async def _persist_alignments(
        self,
        content_id: UUID,
        content_indexed_at: datetime,
        succeeded_goal_ids: set[UUID],
        alignments: list[GoalAlignment],
    ):
        if not succeeded_goal_ids:
            return

        async with transaction() as connection:
            await (
                GoalAlignment.filter(
                    GoalAlignment.filters.by_content(content_id)
                    & GoalAlignment.filters.not_actioned
                    & Q(goal_id__in=list(succeeded_goal_ids))
                    & Q(content_indexed_at=content_indexed_at)
                )
                .using_db(connection)
                .delete()
            )
            for alignment in alignments:
                await alignment.save(using_db=connection)

    async def _score_pair(
        self,
        organization: Organization,
        content: Content,
        goal: Goal,
        similarity: float,
        goal_context: str,
        examples: list[FewShotExample],
        semaphore: asyncio.Semaphore,
    ) -> GoalAlignment | None:
        async with semaphore:
            system_prompt = build_prompt("goal_alignment/score_system.md.jinja")
            user_prompt = build_prompt(
                "goal_alignment/score_user.md.jinja",
                goal_context=goal_context,
                content_type=content.content_type.value,
                content_title=content.title,
                content_body=(content.preview_content or content.index_content)[:2000],
                similarity_score=f"{similarity:.3f}",
                examples=examples,
            )

            judgment = await organization.llm.instructor_completion(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                response_model=AlignmentJudgment,
                model=ALIGNMENT_MODEL,
                temperature=0.0,
            )

            if not judgment.is_aligned or not judgment.signal or not judgment.description:
                return None

            if judgment.alignment_score < MIN_ALIGNMENT_SCORE:
                return None

            return GoalAlignment(
                content_id=content.id,
                goal_id=goal.id,
                content_indexed_at=content.last_indexed_at,
                signal=judgment.signal,
                alignment_score=judgment.alignment_score,
                description=judgment.description,
                organization_id=organization.id,
            )


class EnqueueGoalAlignmentJob(JobDefinition):
    is_recurring = True
    default_queue = JobQueue.MISCELLANEOUS

    async def perform(self):
        organizations = await Organization.all()
        for org in organizations:
            await enqueue_job(ScoreGoalAlignmentJob(organization_id=org.id, unique=True))
