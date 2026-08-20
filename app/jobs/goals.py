from datetime import UTC, datetime, timedelta
from uuid import UUID

from croniter import croniter
from pydantic import BaseModel, Field, field_validator
from sentry_sdk.ai.monitoring import ai_track

from app.jobs.notifications import Notifier
from app.models.accounts import Organization, OrganizationUpdatesConfiguration, User
from app.models.workspaces.goals import Goal, GoalUpdate
from app.prompts.engine import build_prompt
from config import logger
from config.enums import EventAction, JobQueue
from infra.db import transaction
from infra.jobs import JobDefinition, enqueue_job


async def create_goal_update_request(
    goal: Goal,
    question_text: str,
    requested_from_id: UUID,
    *,
    requested_by: User | None = None,
) -> GoalUpdate:
    async with transaction() as connection:
        stale = await GoalUpdate.filter(GoalUpdate.filters.pending_for_goal(goal.id))
        for update in stale:
            await update.close(using_db=connection)

        goal_update = await GoalUpdate.create(
            goal_id=goal.id,
            creator_id=requested_from_id,
            requested_by_id=requested_by.id if requested_by else None,
            status=goal.status,
            question_text=question_text,
            using_db=connection,
        )

        # The owner an update is requested from is reached as a resource-specific action target
        # (GoalNotificationPolicy.action_target_ids), derived from the event — not a caller-supplied
        # recipient.
        notifier = Notifier(resource=goal, current_user=requested_by)
        async with notifier.record_and_notify(
            action=EventAction.GOAL_UPDATE_REQUESTED,
            recordable=goal_update,
            using_db=connection,
        ) as recording:
            recording.event.details["question_text"] = question_text

    return goal_update


TITLE_MODEL = "claude-haiku-4-5"


class GoalTitle(BaseModel):
    title: str | None = Field(
        None,
        description=(
            "A 1-2 word title for the goal, or null if the description is too vague to generate a meaningful title."
        ),
    )

    @field_validator("title")
    @classmethod
    def must_be_at_most_two_words(cls, v: str | None) -> str | None:
        if v and len(v.split()) > 2:
            raise ValueError("Title must be at most 2 words")
        return v


class GenerateGoalTitleJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    goal_id: UUID

    @ai_track("GenerateGoalTitleJob.perform")
    async def perform(self):
        goal = await Goal.get_or_none(id=self.goal_id).prefetch_related(
            "organization", "workspace", "subgoals__workspace"
        )
        if not goal:
            return

        if goal.is_active:
            other_goals = await Goal.filter(Goal.filters.by_active_open_top_level(goal.organization_id)).exclude(
                id=goal.id
            )
        elif goal.planning_list_name:
            other_goals = await Goal.filter(
                Goal.filters.by_organization(goal.organization_id)
                & Goal.filters.by_planning_list_name(goal.planning_list_name)
            ).exclude(id=goal.id)
        else:
            logger.warning(f"Goal {goal.id} is not active and has no planning list - skipping title generation")
            return

        result = await self.generate_title(goal.organization, goal, other_goals)
        if result:
            goal.title = result
            async with goal.workspace.record(EventAction.GOAL_UPDATED) as recording:
                await goal.save(update_fields=["title"], using_db=recording.using_db)
            await self._update_subgoal_titles(goal)

            await goal.broadcast_update()

    async def generate_title(self, organization: Organization, goal: Goal, other_goals: list[Goal]) -> str | None:
        goal_prompt = build_prompt("goals/generate_title_user.md.jinja", goal=goal)
        system_prompt = build_prompt(
            "goals/generate_title_system.md.jinja", organization=organization, other_goals=other_goals
        )
        result = await organization.llm.instructor_completion(goal_prompt, system_prompt, GoalTitle, model=TITLE_MODEL)
        return result.title

    async def _update_subgoal_titles(self, goal: Goal):
        for idx, subgoal in enumerate(sorted(goal.subgoals, key=lambda s: s.created_at), start=1):
            subgoal.title = f"{goal.title}-{idx}"
            async with subgoal.workspace.record(EventAction.GOAL_UPDATED) as recording:
                await subgoal.save(update_fields=["title"], using_db=recording.using_db)


class GenerateGoalUpdatesJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    organization_id: UUID

    async def perform(self):
        config = await OrganizationUpdatesConfiguration.get_or_none(organization_id=self.organization_id)
        question_text = config.goal_update_question if config else None
        if not question_text:
            return

        goals: list[Goal] = await Goal.filter(
            Goal.filters.by_active_open(self.organization_id) & Goal.filters.incomplete
        ).select_related("owner", "workspace")
        if not goals:
            return

        for goal in goals:
            if not goal.owner_id:
                continue

            await create_goal_update_request(goal, question_text, goal.owner_id)


class CheckScheduledUpdatesJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0

    async def perform(self):
        current_time = datetime.now(UTC)

        updates_configs = await OrganizationUpdatesConfiguration.filter(
            update_schedule__isnull=False
        ).prefetch_related("organization")
        if not updates_configs:
            return

        for updates_config in updates_configs:
            if await self._should_generate_updates(updates_config, current_time):
                await enqueue_job(GenerateGoalUpdatesJob(organization_id=updates_config.organization_id))

    async def _should_generate_updates(
        self, updates_config: OrganizationUpdatesConfiguration, current_time: datetime
    ) -> bool:
        """
        Determine if updates should be generated for this organization at the current time
        based on its cron schedule.

        If no schedule is configured, fall back to the default (weekly on Friday at 10:00 UTC).
        """
        if updates_config.update_schedule is None:  # Mypy guard
            return False

        # Check if current time matches the schedule
        cron = croniter(updates_config.update_schedule, current_time)
        previous_cron_schedule: datetime = cron.get_prev(datetime)
        time_diff: timedelta = current_time - previous_cron_schedule
        # If the previous schedule is within the last hour, we should generate updates
        # 3600 assumes the job runs hourly
        return time_diff.total_seconds() < 3600
