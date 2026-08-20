import random
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from sentry_sdk.ai.monitoring import ai_track
from tortoise import BaseDBAsyncClient

from app.jobs.mailers import SendResearchQuestionEmailJob
from app.mailers.research import ScheduledResearchMailer, record_dropped_citation_tokens
from app.models.accounts import Organization, User
from app.models.collaboration.content import (
    CitationTokenMap,
    Content,
    ContentResearchQuery,
    Research,
    ResearchIteration,
    ResearchQuery,
    iter_content_citations,
)
from app.models.commands import ResearchQuestion, ScheduledResearch, ScheduledResearchDelivery
from app.prompts import build_prompt
from app.prompts.engine import current_user_context, organization_context
from config import logger
from config.enums import JobQueue, ResearchSource
from infra.db import transaction
from infra.jobs import JobDefinition, bulk_enqueue_jobs, enqueue_job
from lib.encoding import LLM_ENCODING, chunk_objects, chunk_string

PREPARE_MODEL = "claude-haiku-4-5"

MAX_NUMBER_OF_SEARCH_RESULTS = 10
MAX_NUMBER_OF_FOLLOW_UP_QUESTIONS = 3
MAX_TOKENS_PER_RESULT = 8500
MAX_TOKENS_PER_SOURCE = 2000
MAX_TOTAL_SOURCE_TOKENS = 30000

# Reports are long-form and need a much higher cap than the string_completion default.
REPORT_MAX_TOKENS = 16384


class ResearchQuestionTitle(BaseModel):
    title: str = Field(..., description="The title of the research command.")

    @field_validator("title")
    @classmethod
    def validate_title(cls, value):
        word_count = len(value.split())
        if word_count > 5:
            raise ValueError("Title is too long, must be 5 words or less.")
        return value


class GenerateResearchQuestionTitleJob(JobDefinition):
    default_queue = JobQueue.UI
    research_question_id: UUID

    @ai_track("GenerateResearchQuestionTitleJob.perform")
    async def perform(self):
        question = await ResearchQuestion.get_or_none(id=self.research_question_id).prefetch_related("creator")
        if not question:
            return

        if question.title:
            return

        user = await User.get(id=question.creator_id).prefetch_related("organization")

        user_prompt = question.body
        system_prompt = build_prompt("research/title.md.jinja", **(await organization_context(user.organization)))

        completion = await user.organization.llm.instructor_completion(
            user_prompt, system_prompt, response_model=ResearchQuestionTitle, temperature=0.0
        )

        question.title = completion.title
        await question.save(update_fields=["title"])
        await question.broadcast_progress()


class ResearchJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    research_id: UUID

    async def perform(self):
        async with transaction() as connection:
            research = await Research.get_or_none(id=self.research_id).prefetch_related("organization", "creator")
            if not research:
                return

            first_iteration = ResearchIteration(
                research_id=research.id,
                title="Planning",
                directions=research.topic,
                queries_count=research.max_breadth,
                using_db=connection,
            )
            first_iteration_job = await enqueue_job(
                ResearchIterationJob(research_iteration_id=first_iteration.id, unique=True), using_db=connection
            )

            first_iteration.job_id = first_iteration_job.id
            await first_iteration.save(using_db=connection)


class GeneratedResearchQuery(BaseModel):
    title: str = Field(
        ..., description="A user-facing title for the query, it'll be prefaced with 'Reading about' in the UI"
    )
    terms: str = Field(..., description="The search terms")
    starts_at: datetime | None = Field(None, description="The earliest datetime to allow results")
    ends_at: datetime | None = Field(None, description="The latest datetime to allow results")
    goals: str = Field(
        ...,
        description=(
            "First talk about the goal of the research that this query is meant to accomplish, "
            "then go deeper into how to advance the research once the results are found, mention additional research "
            "directions. Be as specific as possible, especially for additional research directions."
        ),
    )
    source: ResearchSource = Field(ResearchSource.INTERNAL, description="The source to use for this research query")

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: ResearchSource, info: ValidationInfo) -> ResearchSource:
        available_sources = info.context.get("available_sources") if info.context else None
        if available_sources and value not in available_sources:
            raise ValueError(f"{value.value.upper()} source is not available")
        return value


class GeneratedResearchQueryReview(BaseModel):
    learnings: list[str] = Field(..., description="List of learnings")
    follow_up_questions: list[str] = Field(
        ...,
        description=(
            f"List of follow-up questions to research the topic further, max of {MAX_NUMBER_OF_FOLLOW_UP_QUESTIONS}."
        ),
    )
    follow_up_title: str = Field(
        ..., description="A one or two word user-facing title for the follow-up questions, shown as progress in the UI"
    )


class GeneratedResearchQueryNoResultsReview(BaseModel):
    follow_up_questions: list[str] = Field(
        ...,
        description=(f"List of alternative research directions to try, max of {MAX_NUMBER_OF_FOLLOW_UP_QUESTIONS}."),
    )
    follow_up_title: str = Field(
        ..., description="A short user-facing title for the follow-up directions, shown as progress in the UI"
    )


class ResearchIterationJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    research_iteration_id: UUID

    @ai_track("ResearchIterationJob.perform")
    async def perform(self):
        iteration = await ResearchIteration.get_or_none(id=self.research_iteration_id).prefetch_related(
            "research__creator__organization", "research__iterations__queries"
        )
        if not iteration:
            return

        queries = await self._generate_queries(iteration)

        async with transaction() as connection:
            for query in queries:
                query_json = query.model_dump_json()
                await enqueue_job(
                    ResearchQueryJob(iteration_id=iteration.id, generated_query_data=query_json, unique=True),
                    using_db=connection,
                )

    async def _generate_queries(self, iteration: ResearchIteration) -> list[GeneratedResearchQuery]:
        research_sources = get_research_sources(iteration.research.creator)

        question = await ResearchQuestion.filter(research_id=iteration.research_id).first()
        thread_context = await question.get_thread_context() if question else []

        user_prompt = build_prompt(
            "research/generate_queries.md.jinja",
            iteration=iteration,
            available_sources=research_sources.keys(),
            research_source=ResearchSource,
            thread_context=thread_context,
        )
        system_prompt = build_prompt(
            "research/system.md.jinja",
            **(await current_user_context(iteration.research.creator)),
        )
        results = await iteration.research.creator.organization.llm.instructor_completion(
            user_prompt,
            system_prompt,
            response_model=list[GeneratedResearchQuery],
            temperature=0.0,
            context={"available_sources": set(research_sources.keys())},
        )

        return results


class ResearchQueryJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    iteration_id: UUID
    generated_query_data: str

    async def perform(self):
        iteration = await ResearchIteration.get_or_none(id=self.iteration_id).prefetch_related(
            "research__creator__organization"
        )
        if not iteration:
            return

        generated_query = GeneratedResearchQuery.model_validate_json(self.generated_query_data)

        research_sources = get_research_sources(iteration.research.creator)
        search = research_sources[generated_query.source](iteration, generated_query)

        await search.perform()
        if not search.research_query:
            raise ValueError("Research query was not created")

        if search.results:
            review = await self._review_query_results(iteration, search.research_query, search.results)
            await search.research_query.mark_completed(review.learnings)
        else:
            review = await self._review_no_results(iteration, search.research_query)
            await search.research_query.mark_completed()

        if iteration.is_within_depth:
            await self._start_next_iteration(iteration, search.research_query, review)

        await self._check_research_completion(iteration)

    async def _review_query_results(
        self, iteration: ResearchIteration, research_query: ResearchQuery, results: Sequence[Content]
    ):
        for result in results:
            chunked_content = chunk_string(result.index_content, MAX_TOKENS_PER_RESULT, LLM_ENCODING)
            result.index_content = chunked_content[0]

        token_map = CitationTokenMap.for_sources([r.id for r in results])
        citation_ids = {r.id: token_map.token_for(r.id) for r in results}

        user_prompt = build_prompt(
            "research/review_results.md.jinja",
            iteration=iteration,
            query=research_query,
            results=results,
            citation_ids=citation_ids,
            max_learnings=iteration.research.max_learnings,
        )
        system_prompt = build_prompt(
            "research/system.md.jinja",
            **(await current_user_context(iteration.research.creator)),
        )

        review = await research_query.research.creator.organization.llm.instructor_completion(
            user_prompt, system_prompt, response_model=GeneratedResearchQueryReview, temperature=0.0
        )
        # Storage stays canonical UUID: detokenize the model's S-tokens before the learnings persist.
        detokenized = token_map.detokenize_all(review.learnings)
        review.learnings = detokenized.texts
        record_dropped_citation_tokens(
            boundary="extraction",
            dropped_tokens=detokenized.dropped,
            total_citation_count=detokenized.total,
            research_id=iteration.research_id,
        )
        return review

    async def _review_no_results(
        self, iteration: ResearchIteration, research_query: ResearchQuery
    ) -> GeneratedResearchQueryNoResultsReview:
        await iteration.fetch_related("research__creator__organization", "research__iterations__queries")
        user_prompt = build_prompt(
            "research/review_no_results.md.jinja",
            iteration=iteration,
            query=research_query,
        )
        system_prompt = build_prompt(
            "research/system.md.jinja",
            **(await current_user_context(iteration.research.creator)),
        )

        return await research_query.research.creator.organization.llm.instructor_completion(
            user_prompt, system_prompt, response_model=GeneratedResearchQueryNoResultsReview, temperature=0.0
        )

    async def _start_next_iteration(
        self,
        previous_iteration: ResearchIteration,
        query: ResearchQuery,
        review: GeneratedResearchQueryReview | GeneratedResearchQueryNoResultsReview,
    ):
        next_directions = (
            f"Previous research goal: {query.goals}\n\n"
            f"Follow-up research directions: \n- "
            f"{'\n- '.join(review.follow_up_questions)}"
        )

        async with transaction() as connection:
            next_iteration = ResearchIteration(
                research_id=previous_iteration.research_id,
                title=review.follow_up_title,
                directions=next_directions,
                queries_count=max(1, previous_iteration.queries_count // 2),
                depth=previous_iteration.depth + 1,
                using_db=connection,
            )
            next_iteration_job = await enqueue_job(
                ResearchIterationJob(research_iteration_id=next_iteration.id, unique=True), using_db=connection
            )

            next_iteration.job_id = next_iteration_job.id
            await next_iteration.save(using_db=connection)

    async def _check_research_completion(self, iteration: ResearchIteration):
        research = await Research.get(id=iteration.research_id).prefetch_related("iterations__queries")
        if not research.is_completed:
            return

        # A research is either driven by a ResearchQuestion (one-off) or a ScheduledResearchDelivery
        # (scheduled), never both — return as soon as we find the matching record.
        research_question = await ResearchQuestion.get_or_none(research_id=research.id)
        if research_question:
            if not research_question.is_response_complete:
                await enqueue_job(ResearchQuestionCompleteJob(research_question_id=research_question.id, unique=True))
            return

        delivery = await ScheduledResearchDelivery.get_or_none(research_id=research.id, delivered_at__isnull=True)
        if delivery:
            await enqueue_job(
                PublishScheduledResearchJob(
                    scheduled_research_id=delivery.scheduled_research_id,
                    research_id=research.id,
                    unique=True,
                )
            )


@dataclass
class ResearchSearch:
    iteration: ResearchIteration
    generated_query: GeneratedResearchQuery
    research_query: ResearchQuery | None = None
    results: Sequence[Content] = field(default_factory=list)

    async def perform(self):
        raise NotImplementedError


@dataclass
class ResearchInternalSearch(ResearchSearch):
    async def perform(self):
        self.research_query = await ResearchQuery.create(
            iteration_id=self.iteration.id,
            research_id=self.iteration.research_id,
            research=self.iteration.research,
            title=self.generated_query.title,
            starts_at=self.generated_query.starts_at,
            ends_at=self.generated_query.ends_at,
            goals=self.generated_query.goals,
            source=self.generated_query.source,
        )

        search = ContentResearchQuery(
            organization=self.iteration.research.creator.organization,
            query=self.generated_query.terms,
            user=self.iteration.research.creator,
            starts_at=self.research_query.starts_at,
            ends_at=self.research_query.ends_at,
            limit=MAX_NUMBER_OF_SEARCH_RESULTS,
        )

        self.results = await search.execute()
        await self.research_query.save_content_search(search, self.results)


def prepare_tokenized_source_content(
    results: Sequence[Content],
    learnings: Collection[str],
    token_budget: int = MAX_TOTAL_SOURCE_TOKENS,
) -> tuple[list[dict], CitationTokenMap]:
    # Builds the source dicts the synthesis prompts render *and* the token map that round-trips
    # citations, together: each source's `citation_id` is its S-token from the outset, so the raw
    # Content UUID is never a value the prompt could render. The two are one step because they are
    # only ever correct as a pair — a source dict without its token would leak a UUID to the model.
    def truncated_content(result: Content) -> str:
        return chunk_string(result.index_content, MAX_TOKENS_PER_SOURCE, LLM_ENCODING)[0]

    selected = next(
        iter(chunk_objects(results, truncated_content, token_budget, LLM_ENCODING)),
        [],
    )

    # Union selected-source ids with ids already cited in the carried learnings: a carried learning
    # may cite a source the token budget dropped from `selected`, and that citation is still valid.
    # for_sources de-duplicates in first-appearance order, so the selected sources keep S1..Sn.
    ids: list[UUID] = [result.id for result in selected]
    for learning in learnings:
        ids.extend(iter_content_citations(learning))
    token_map = CitationTokenMap.for_sources(ids)

    content_results = [
        {
            "id": str(result.id),
            "citation_id": token_map.token_for(result.id),
            "title": result.title,
            "author": result.author,
            "created_at": result.created_at,
            "source_url": result.source_url,
            "content": truncated_content(result),
        }
        for result in selected
    ]
    return content_results, token_map


class ResearchQuestionCompleteJob(JobDefinition):
    default_queue = JobQueue.UI
    research_question_id: UUID

    async def perform(self):
        question = await ResearchQuestion.get_or_none(id=self.research_question_id).prefetch_related(
            "research__iterations__queries", "creator__organization"
        )
        if not question:
            return

        if not question.research:
            return

        # Skip the expensive LLM synthesis when a duplicate completion job already finished. The lock
        # below covers the concurrent case; this short-circuits the common sequential one.
        if question.is_response_complete:
            return

        thread_context = await question.get_thread_context(max_tokens=10000)

        results = await question.research.fetch_results()
        learnings = question.research.learnings
        content_results, token_map = prepare_tokenized_source_content(results, learnings)
        learnings = [token_map.tokenize_uuid_markers(learning) for learning in learnings]

        system_prompt = build_prompt(
            "research/command.md.jinja",
            **(await current_user_context(question.creator)),
            research_question=question,
            thread_context=thread_context,
        )
        user_prompt = build_prompt("research/findings.md.jinja", learnings=learnings, content_results=content_results)
        result = await question.creator.organization.llm.string_completion(
            user_prompt, system_prompt, temperature=0.0, max_tokens=REPORT_MAX_TOKENS
        )

        # Storage stays canonical UUID: detokenize the report before it is recorded and mailed.
        detokenized = token_map.detokenize_all([result])
        result = detokenized.texts[0]
        record_dropped_citation_tokens(
            boundary="synthesis",
            dropped_tokens=detokenized.dropped,
            total_citation_count=detokenized.total,
            research_id=question.research.id,
            research_question_id=question.id,
        )

        # Parallel query jobs can each enqueue this completion job, and unique=True won't dedup them
        # (non-atomic SELECT-then-INSERT, no constraint). Lock the question and re-check so only the
        # first run records the response and sends the email.
        async with transaction() as connection:
            locked = await ResearchQuestion.select_for_update().using_db(connection).get_or_none(id=question.id)
            if not locked or locked.is_response_complete:
                return

            await locked.mark_completed(result, using_db=connection)
            await enqueue_job(
                SendResearchQuestionEmailJob(research_question_id=self.research_question_id, unique=True),
                using_db=connection,
            )


research_source_registry: dict[ResearchSource, tuple[type[ResearchSearch], Callable[[User], bool]]] = {
    ResearchSource.INTERNAL: (ResearchInternalSearch, lambda user: True),
}


def register_research_source(
    research_source: ResearchSource, constructor: type[ResearchSearch], is_configured: Callable[[User], bool]
) -> None:
    research_source_registry[research_source] = (constructor, is_configured)


def get_research_sources(user: User) -> dict[ResearchSource, type[ResearchSearch]]:
    sources: dict[ResearchSource, type[ResearchSearch]] = {}
    for research_source, (constructor, is_configured) in research_source_registry.items():
        if is_configured(user):
            sources[research_source] = constructor

    return sources


async def start_research_from_question(
    question: ResearchQuestion, using_db: BaseDBAsyncClient | None = None
) -> Research:
    async with transaction(using_db) as connection:
        research = await Research.create(
            topic=question.body,
            sources=question.sources,
            creator_id=question.creator_id,
            organization_id=question.creator.organization_id,
            using_db=connection,
        )

        research_job = ResearchJob(research_id=research.id)
        title_job = GenerateResearchQuestionTitleJob(research_question_id=question.id)

        job = await enqueue_job(research_job, using_db=connection)
        await enqueue_job(title_job, using_db=connection)

        research.job_id = job.id
        await research.save(using_db=connection, update_fields=["job_id"])

        question.research_id = research.id
        await question.save(using_db=connection, update_fields=["research_id"])

        return research


#
# Scheduled research
#
#


# Jitter + per-schedule stagger avoids a thundering herd when many schedules fire on the same cron tick.
CHECK_SCHEDULED_RESEARCH_JITTER_SECONDS = 600
CHECK_SCHEDULED_RESEARCH_STAGGER_SECONDS = 30


class PreparedScheduledResearch(BaseModel):
    title: str = Field(description="A short user-facing title for the schedule, max 5 words.")
    topic_prompt: str = Field(description="The research intent, stripped of formatting directives.")
    formatting_prompt: str | None = Field(
        default=None, description="Formatting directives, or null if the prompt has none."
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if len(value.split()) > 5:
            raise ValueError("Title must be 5 words or fewer.")
        return value

    @classmethod
    async def generate(cls, organization: Organization, prompt: str) -> "PreparedScheduledResearch":
        system_prompt = build_prompt("scheduled_research/prepare.md.jinja")
        return await organization.llm.instructor_completion(
            prompt,
            system_prompt,
            response_model=cls,
            model=PREPARE_MODEL,
            temperature=0.0,
        )


class PrepareScheduledResearchJob(JobDefinition):
    default_queue = JobQueue.UI
    scheduled_research_id: UUID

    @ai_track("PrepareScheduledResearchJob.perform")
    async def perform(self):
        schedule = await ScheduledResearch.get_or_none(id=self.scheduled_research_id).prefetch_related("organization")
        if not schedule:
            return

        try:
            prepared = await PreparedScheduledResearch.generate(schedule.organization, schedule.prompt)
            schedule.title = prepared.title
            schedule.topic_prompt = prepared.topic_prompt
            schedule.formatting_prompt = prepared.formatting_prompt
            schedule.preparation_failed_at = None
        except Exception:
            # Instructor's internal retries exhausted; surfacing the retry affordance is better than
            # silently running with the raw prompt. Return success so Cloud Tasks stops retrying.
            logger.exception("Preparation failed for scheduled_research %s", schedule.id)
            schedule.preparation_failed_at = datetime.now(UTC)

        await schedule.save()
        await schedule.broadcast_prepared()


class CheckScheduledResearchJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0

    async def perform(self):
        schedules = await ScheduledResearch.all().prefetch_related("creator")
        now = datetime.now(UTC)
        due: list[ScheduledResearchJob] = []
        for schedule in schedules:
            if not schedule.is_recurring_now:
                continue
            # Cheap in-memory idempotency gate: skip schedules already delivered for the current refresh window,
            # so a delayed retry from the previous tick doesn't stack a second run on top of this one.
            if schedule.last_delivered_at and schedule.last_delivered_at >= schedule.last_refresh_scheduled_at:
                continue
            jitter_seconds = random.uniform(0, CHECK_SCHEDULED_RESEARCH_JITTER_SECONDS) + (
                len(due) * CHECK_SCHEDULED_RESEARCH_STAGGER_SECONDS
            )
            due.append(
                ScheduledResearchJob(
                    scheduled_research_id=schedule.id,
                    perform_at=now + timedelta(seconds=jitter_seconds),
                )
            )

        if due:
            await bulk_enqueue_jobs(due)


class ScheduledResearchJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    scheduled_research_id: UUID
    # force=True bypasses the "already delivered this window" gate for explicit user action (run_now),
    # which would otherwise silently no-op after the scheduled fire has already run today.
    force: bool = False

    async def perform(self):
        async with transaction() as connection:
            # Row lock + re-check last_delivered_at guards against two concurrent runs for the same schedule
            # (e.g. a delayed retry overlapping a fresh heartbeat tick).
            schedule = (
                await ScheduledResearch.select_for_update()
                .using_db(connection)
                .prefetch_related("creator")
                .get_or_none(id=self.scheduled_research_id)
            )
            if not schedule:
                return

            if (
                not self.force
                and schedule.last_delivered_at
                and schedule.last_delivered_at >= schedule.last_refresh_scheduled_at
            ):
                return

            research = Research(
                topic=schedule.effective_topic_prompt,
                sources=schedule.sources,
                creator_id=schedule.creator_id,
                organization_id=schedule.organization_id,
            )
            research.apply_default_parameters()
            await research.save(using_db=connection)

            await ScheduledResearchDelivery.create(
                scheduled_research_id=schedule.id,
                research_id=research.id,
                using_db=connection,
            )

            job = await enqueue_job(ResearchJob(research_id=research.id), using_db=connection)
            research.job_id = job.id
            await research.save(using_db=connection, update_fields=["job_id"])


class PublishScheduledResearchJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    scheduled_research_id: UUID
    research_id: UUID

    @ai_track("PublishScheduledResearchJob.perform")
    async def perform(self):
        schedule = await ScheduledResearch.get_or_none(id=self.scheduled_research_id).prefetch_related(
            "creator", "organization"
        )
        if not schedule:
            return

        research = await Research.get_or_none(id=self.research_id).prefetch_related("iterations__queries")
        if not research:
            return

        results = await research.fetch_results()
        content_results, token_map = prepare_tokenized_source_content(results, research.learnings)
        learnings = [token_map.tokenize_uuid_markers(learning) for learning in research.learnings]

        findings_prompt = build_prompt(
            "scheduled_research/show.md.jinja",
            research=research,
            learnings=learnings,
            content_results=content_results,
        )
        system_prompt = build_prompt(
            "scheduled_research/summary.md.jinja",
            topic_prompt=schedule.effective_topic_prompt,
            formatting_prompt=schedule.formatting_prompt,
            sources=schedule.sources,
        )
        rendered = await schedule.organization.llm.string_completion(
            findings_prompt, system_prompt, temperature=0.0, max_tokens=REPORT_MAX_TOKENS
        )

        # Storage stays canonical UUID: detokenize before the mailer records and sends the report.
        detokenized = token_map.detokenize_all([rendered])
        rendered = detokenized.texts[0]
        record_dropped_citation_tokens(
            boundary="synthesis",
            dropped_tokens=detokenized.dropped,
            total_citation_count=detokenized.total,
            research_id=research.id,
        )

        await ScheduledResearchMailer(
            scheduled_research=schedule, research=research, rendered_markdown=rendered
        ).send()

        now = datetime.now(UTC)
        async with transaction() as connection:
            schedule.last_delivered_at = now
            await schedule.save(update_fields=["last_delivered_at", "updated_at"], using_db=connection)
            await (
                ScheduledResearchDelivery.filter(
                    scheduled_research_id=self.scheduled_research_id,
                    research_id=self.research_id,
                )
                .using_db(connection)
                .update(delivered_at=now, updated_at=now)
            )
