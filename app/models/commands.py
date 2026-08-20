from dataclasses import dataclass
from datetime import UTC, datetime
from re import RegexFlag
from typing import Annotated, Any, ClassVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import tiktoken
from croniter import croniter
from tortoise import BaseDBAsyncClient, fields
from tortoise.queryset import Q
from tortoise.signals import post_save
from tortoise.validators import RegexValidator

from app.models.accounts import Organization, User
from app.models.collaboration.content import Research
from config.enums import CommandType, ResearchQuestionStatus, ResearchSource, ScheduledResearchFrequency
from infra.db import JSONField, RecordModel, SoftDeleteableMixin, after_commit
from infra.messaging import Topic
from lib.encoding import LLM_ENCODING

_tokenizer = tiktoken.get_encoding(LLM_ENCODING)

#
# Commands
#
#


@dataclass
class Command:
    key: str
    type: CommandType
    label: str
    description: str | None = None
    url: str | None = None
    options: dict[str, Any] | None = None


SYSTEM_COMMANDS = [
    Command(
        key="research",
        type=CommandType.RESEARCH,
        label="Research",
        description="Kick off research and receive a report when it is done",
    ),
    Command(
        key="create_quick_link",
        type=CommandType.CREATE_QUICK_LINK,
        label="Create quick link",
        description="Create a quick link to any URL and add it as a command",
    ),
]


#
# Quick Links
#
#


class QuickLinkFilters:
    @staticmethod
    def by_id(id: UUID):
        return Q(id=id)

    @staticmethod
    def by_owner(owner_id: UUID):
        return Q(owner_id=owner_id)


class QuickLink(RecordModel):
    label: str = fields.TextField()
    url: str | None = fields.TextField(null=True)
    open_in_new_tab = fields.BooleanField(default=False)
    owner: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User", related_name="quick_links")
    owner_id: Annotated[UUID, "foreign key to owner user"]
    filters = QuickLinkFilters()

    @property
    def command_options(self) -> dict[str, Any]:
        return {"open_in_new_tab": self.open_in_new_tab, "editable": True}

    @property
    def as_command(self):
        return Command(
            key=str(self.id),
            type=CommandType.QUICK_LINK,
            label=self.label,
            url=self.url,
            options=self.command_options,
        )


#
# Research
#
#


class ResearchQuestionFilters:
    pending: ClassVar[Q] = Q(research_id__isnull=True)
    not_completed: ClassVar[Q] = Q(response_completed_at__isnull=True)

    @staticmethod
    def by_creator(creator_id: UUID):
        return Q(creator_id=creator_id)


class ResearchQuestion(RecordModel):
    body: str = fields.TextField(
        validators=[RegexValidator(r"\S+", RegexFlag.IGNORECASE)], description="protected_column"
    )
    title: str | None = fields.TextField(null=True)
    sources: list[ResearchSource] = JSONField(default=[])
    response: str = fields.TextField(null=True, description="protected_column")
    response_completed_at = fields.DatetimeField(null=True)
    response_message_id: str | None = fields.TextField(null=True)
    research: fields.ForeignKeyNullableRelation[Research] = fields.ForeignKeyField("convictional.Research", null=True)
    research_id: Annotated[UUID | None, "foreign key to research"]
    creator: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    creator_id: Annotated[UUID, "foreign key to creator user"]
    in_reply_to_message_id: str | None = fields.TextField(null=True)
    in_reply_to_subject: str | None = fields.TextField(null=True)
    replying_to_message_id: str | None = fields.TextField(null=True)
    cc_recipients: list[str] = JSONField(default=[])
    filters = ResearchQuestionFilters()

    class Meta:
        ordering = ["created_at"]
        indexes = (("research_id",), ("response_message_id",))

    @property
    def status(self) -> ResearchQuestionStatus:
        if self.response_completed_at is not None:
            return ResearchQuestionStatus.COMPLETED
        if self.research_id is not None:
            return ResearchQuestionStatus.STARTED
        return ResearchQuestionStatus.PENDING

    @property
    def is_response_complete(self):
        return bool(self.response) and self.response_completed_at is not None

    @property
    def is_email_reply(self) -> bool:
        return self.in_reply_to_message_id is not None or self.replying_to_message_id is not None

    async def get_thread_context(
        self, max_tokens: int = 10000, prefetch: list[str] | None = None
    ) -> list["ResearchQuestion"]:
        if not self.replying_to_message_id:
            return []

        # Grab all completed questions by this creator that have a response_message_id, then build the chain in memory
        # This avoids n+1 queries when traversing the reply chain
        query = ResearchQuestion.filter(
            creator_id=self.creator_id,
            response_completed_at__isnull=False,
            response_message_id__isnull=False,
        ).exclude(id=self.id)
        if prefetch:
            query = query.prefetch_related(*prefetch)
        completed_questions = await query

        by_response_id = {q.response_message_id: q for q in completed_questions}

        chain: list[ResearchQuestion] = []
        replying_to_message_id: str | None = self.replying_to_message_id

        # Build out the chain in reverse chronological order
        while replying_to_message_id:
            prior = by_response_id.get(replying_to_message_id)
            if not prior:
                break
            chain.append(prior)
            replying_to_message_id = prior.replying_to_message_id

        # Truncate to token budget, keeping most recent items
        truncated_chain = _truncate_to_token_budget(chain, max_tokens)
        # Return in chronological order
        return list(reversed(truncated_chain))

    async def mark_completed(self, response: str, using_db: BaseDBAsyncClient | None = None):
        self.response = response
        self.response_completed_at = datetime.now(UTC)
        await self.save(update_fields=["response", "response_completed_at"], using_db=using_db)
        await self.broadcast_progress()

    async def broadcast_progress(self, **data):
        async def broadcast(using_db: BaseDBAsyncClient):
            broadcast_data = data or {}
            broadcast_data.update(id=self.id, status=self.status.value)
            await Topic("research_progress", user_id=self.creator_id).broadcast(**broadcast_data)

        await after_commit(broadcast)


def _truncate_to_token_budget(questions: list["ResearchQuestion"], max_tokens: int) -> list["ResearchQuestion"]:
    total_tokens = 0
    result: list[ResearchQuestion] = []

    for question in questions:
        text = f"Question: {question.body}\n\nResponse: {question.response or ''}\n"
        tokens = len(_tokenizer.encode(text))
        if total_tokens + tokens > max_tokens:
            break
        result.append(question)
        total_tokens += tokens

    return result


@post_save(ResearchQuestion)
async def broadcast_research_question_progress(
    sender: "type[ResearchQuestion]",
    instance: ResearchQuestion,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    if created:
        await instance.broadcast_progress()


#
# Scheduled research
#
#


SCHEDULED_RESEARCH_DEFAULT_TITLE = "Untitled"
# Must stay >= the Cloud Scheduler heartbeat cadence in scheduler.tf so a schedule firing
# inside the jitter+stagger window of its cron is still considered "recurring now" on the next heartbeat check.
SCHEDULED_RESEARCH_RECURRING_NOW_WINDOW_SECONDS = 3600

_SCHEDULE_DAY_NAMES = {
    "0": "Sunday",
    "1": "Monday",
    "2": "Tuesday",
    "3": "Wednesday",
    "4": "Thursday",
    "5": "Friday",
    "6": "Saturday",
}


class ScheduledResearchFilters:
    @staticmethod
    def by_creator(creator_id: UUID) -> Q:
        return Q(creator_id=creator_id)


class ScheduledResearch(SoftDeleteableMixin, RecordModel):
    title: str = fields.TextField(default=SCHEDULED_RESEARCH_DEFAULT_TITLE)
    prompt: str = fields.TextField()
    topic_prompt: str | None = fields.TextField(null=True)
    formatting_prompt: str | None = fields.TextField(null=True)
    preparation_failed_at: datetime | None = fields.DatetimeField(null=True)
    schedule_cron = fields.CharField(max_length=255)
    sources: list[ResearchSource] = JSONField(default=list)
    last_delivered_at: datetime | None = fields.DatetimeField(null=True)
    creator: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    creator_id: Annotated[UUID, "foreign key to creator user"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")
    organization_id: Annotated[UUID, "foreign key to organization"]
    filters = ScheduledResearchFilters()

    class Meta:
        ordering = ["-created_at"]
        indexes = (("creator_id",),)

    @property
    def is_untitled(self) -> bool:
        return self.title == SCHEDULED_RESEARCH_DEFAULT_TITLE

    @property
    def effective_topic_prompt(self) -> str:
        # Fallback covers the brief in-flight preparation window. After preparation_failed_at is set the UI
        # surfaces a retry affordance; the model itself always returns a usable prompt for the publish step.
        return self.topic_prompt or self.prompt

    @property
    def _cron_parts(self) -> list[str]:
        return self.schedule_cron.split() if self.schedule_cron else []

    @property
    def frequency(self) -> ScheduledResearchFrequency:
        parts = self._cron_parts
        if not parts:
            return ScheduledResearchFrequency.WEEKLY
        day_of_week = parts[4]
        if day_of_week == "*":
            return ScheduledResearchFrequency.DAILY
        if day_of_week == "1-5":
            return ScheduledResearchFrequency.WEEKDAYS
        return ScheduledResearchFrequency.WEEKLY

    @property
    def hour(self) -> int:
        parts = self._cron_parts
        return int(parts[1]) if parts else 9

    @property
    def day_of_week(self) -> str | None:
        parts = self._cron_parts
        if not parts:
            return "1"
        return parts[4] if self.frequency == ScheduledResearchFrequency.WEEKLY else None

    @property
    def timezone(self) -> ZoneInfo:
        # Defensive fallback: the hourly heartbeat iterates every schedule, so one bad time_zone value
        # shouldn't take out the whole run.
        if self.creator and self.creator.time_zone:
            try:
                return ZoneInfo(self.creator.time_zone)
            except ZoneInfoNotFoundError:
                pass
        return ZoneInfo("UTC")

    @property
    def last_refresh_scheduled_at(self) -> datetime:
        previous, _ = self._cron_window()
        return previous

    @property
    def is_recurring_now(self) -> bool:
        _, elapsed = self._cron_window()
        return elapsed < SCHEDULED_RESEARCH_RECURRING_NOW_WINDOW_SECONDS

    def _cron_window(self) -> tuple[datetime, float]:
        # Returns (most-recent scheduled fire, seconds since that fire). The "current scheduled fire" framing
        # is what the idempotency gate in CheckScheduledResearchJob / ScheduledResearchJob relies on: a
        # schedule has already been handled for this window iff last_delivered_at >= last_refresh_scheduled_at.
        now = datetime.now(self.timezone)
        previous: datetime = croniter(self.schedule_cron, now).get_prev(datetime)
        elapsed = (now - previous).total_seconds()
        return previous.replace(tzinfo=self.timezone), elapsed

    def validate_schedule(
        self,
        frequency: ScheduledResearchFrequency,
        hour: int,
        day_of_week: str | None = None,
    ) -> str | None:
        if not (0 <= hour < 24):
            return "Hour must be between 0 and 23"

        if frequency == ScheduledResearchFrequency.WEEKLY:
            if day_of_week is None or day_of_week not in ("0", "1", "2", "3", "4", "5", "6"):
                return "Day of week must be between 0 (Sunday) and 6 (Saturday) for weekly frequency"
        elif frequency not in (ScheduledResearchFrequency.DAILY, ScheduledResearchFrequency.WEEKDAYS):
            return "Invalid frequency value"

        if not croniter.is_valid(self._build_cron_expression(frequency, hour, day_of_week)):
            return "Unknown schedule error"
        return None

    def set_schedule(
        self,
        frequency: ScheduledResearchFrequency,
        hour: int,
        day_of_week: str | None = None,
    ) -> None:
        self.schedule_cron = self._build_cron_expression(frequency, hour, day_of_week)

    def _build_cron_expression(
        self,
        frequency: ScheduledResearchFrequency,
        hour: int,
        day_of_week: str | None,
    ) -> str:
        if frequency == ScheduledResearchFrequency.DAILY:
            return f"0 {hour} * * *"
        if frequency == ScheduledResearchFrequency.WEEKDAYS:
            return f"0 {hour} * * 1-5"
        if frequency == ScheduledResearchFrequency.WEEKLY:
            if day_of_week is None:
                raise ValueError("Day of week must be provided for weekly frequency")
            return f"0 {hour} * * {day_of_week}"
        raise ValueError("Invalid frequency value")

    @property
    def next_run_at(self) -> datetime | None:
        if not self.schedule_cron:
            return None
        cron = croniter(self.schedule_cron, datetime.now(self.timezone))
        next_run: datetime = cron.get_next(datetime)
        return next_run.replace(tzinfo=self.timezone)

    @property
    def schedule_description(self) -> str:
        if self.frequency == ScheduledResearchFrequency.DAILY:
            return f"Daily at {self.hour:02d}:00"
        if self.frequency == ScheduledResearchFrequency.WEEKDAYS:
            return f"Weekdays at {self.hour:02d}:00"
        name = _SCHEDULE_DAY_NAMES.get(self.day_of_week or "1", "Monday")
        return f"Weekly on {name} at {self.hour:02d}:00"

    async def broadcast_prepared(self) -> None:
        async def broadcast(_using_db: BaseDBAsyncClient) -> None:
            await Topic("scheduled_research", user_id=str(self.creator_id)).broadcast(
                action="prepared", schedule_id=str(self.id), title=self.title
            )

        await after_commit(broadcast)


class ScheduledResearchDelivery(RecordModel):
    # Mirrors ResearchQuestion's role for the scheduled path: its presence on a Research is the
    # signal _check_research_completion uses to enqueue PublishScheduledResearchJob.
    scheduled_research: fields.ForeignKeyRelation[ScheduledResearch] = fields.ForeignKeyField(
        "convictional.ScheduledResearch", related_name="deliveries"
    )
    scheduled_research_id: Annotated[UUID, "foreign key to scheduled research"]
    research: fields.ForeignKeyRelation[Research] = fields.ForeignKeyField(
        "convictional.Research", related_name="scheduled_research_deliveries"
    )
    research_id: Annotated[UUID, "foreign key to research"]
    delivered_at: datetime | None = fields.DatetimeField(null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = (("research_id",), ("scheduled_research_id",))
