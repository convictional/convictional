from dataclasses import dataclass
from typing import Optional, Self
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.accounts import User
from app.models.collaboration.mailbox import (
    MailboxView,
    MailboxViewCache,
    MailboxViewCacheData,
    MailboxViewIdentifier,
)
from app.models.workspaces.goals import Goal
from app.presenters.mailbox_entries import MailboxEntryPresenter
from config.enums import MailboxViewLayout

# Custom Views and Custom Sorts are capped independently so a user with many of one kind never
# starves the other out of the combined `all_views` list the client splits by layout.
ALL_VIEWS_LIMIT_PER_LAYOUT = 10


class ViewSection(BaseModel):
    title: str = Field(default="", description="Short title for this section")
    description: str = Field(default="", description="Brief description of what belongs in this section")
    mailbox_entry_ids: list[str] = Field(default_factory=list, description="List of mailbox entry UUIDs")
    goal_id: Optional[str] = Field(default=None, description="ID of the goal this section relates to, if any")  # noqa: UP045 - instructor Partial requires Optional


# The LLM references items by their 1-based position in the prompt list ("Item N") rather than by
# UUID. Models reliably copy a small integer but routinely truncate, duplicate, or mangle 36-char
# UUIDs when transcribing them by hand — that corruption silently dropped posts/chats and blanked
# whole views. The session maps these numbers back to real ids before anything is cached or
# broadcast, so the rest of the pipeline still works in `ViewSection` with valid UUIDs.
class LLMViewSection(BaseModel):
    title: str = Field(default="", description="Short title for this section")
    description: str = Field(default="", description="Brief description of what belongs in this section")
    entry_numbers: list[int] = Field(
        default_factory=list,
        description="The item numbers (the integer N from 'Item N' in the list above) that belong in this section",
    )
    goal_id: Optional[str] = Field(default=None, description="ID of the goal this section relates to, if any")  # noqa: UP045 - instructor Partial requires Optional


class LLMMailboxViewResponse(BaseModel):
    sections: list[LLMViewSection] = Field(default_factory=list, description="Sections organizing the items")


# Ranked sorts ask the LLM to *score* each item against the request; the server sorts
# deterministically. A dedicated schema (not the grouped sections shape) keeps the model's job
# unambiguous and never weakens the grouped section gate. Like `LLMViewSection`, items are
# referenced by their 1-based "Item N" number rather than by UUID.
class LLMRankedEntry(BaseModel):
    entry_number: Optional[int] = Field(  # noqa: UP045 - instructor Partial requires Optional
        default=None, description="The item number (the integer N from 'Item N' in the list above)"
    )
    score: Optional[float] = Field(  # noqa: UP045 - instructor Partial requires Optional
        default=None, ge=0.0, le=1.0, description="Priority against the request, 1.0 = highest, 0.0 = irrelevant"
    )


class LLMMailboxRankResponse(BaseModel):
    entries: list[LLMRankedEntry] = Field(default_factory=list, description="A score for every item")


@dataclass
class MailboxViewPresenter:
    active: MailboxView | None
    active_template: MailboxViewIdentifier | None
    cache_data: MailboxViewCacheData | None
    all_views: list[MailboxView]
    is_not_found: bool = False
    has_goals_for_view: bool = False

    @classmethod
    async def create(
        cls,
        user: User,
        mailbox_view_id: UUID | None = None,
        mailbox_view_template: str | None = None,
        goal_id: UUID | None = None,
    ) -> Self:
        active = None
        active_template = None
        is_not_found = False
        cache_data = None

        # Template takes precedence if both provided
        if mailbox_view_template:
            active_template = MailboxViewIdentifier.for_template(mailbox_view_template, goal_id=goal_id)
            if active_template:
                cache_data = await active_template.read_cache(user.id)
            else:
                is_not_found = True
        elif mailbox_view_id:
            active = await MailboxView.get_or_none(
                id=mailbox_view_id, user_id=user.id, organization_id=user.organization_id
            )
            is_not_found = active is None
            if active:
                cache_data = await MailboxViewCache(active).read()

        grouped_views = (
            await MailboxView.filter(MailboxView.filters.by_user(user.id))
            .filter(MailboxView.filters.by_organization(user.organization_id))
            .filter(layout=MailboxViewLayout.GROUPED)
            .order_by("-created_at")
            .limit(ALL_VIEWS_LIMIT_PER_LAYOUT)
        )
        ranked_views = (
            await MailboxView.filter(MailboxView.filters.by_user(user.id))
            .filter(MailboxView.filters.by_organization(user.organization_id))
            .filter(layout=MailboxViewLayout.RANKED)
            .order_by("-created_at")
            .limit(ALL_VIEWS_LIMIT_PER_LAYOUT)
        )
        all_views = [*grouped_views, *ranked_views]

        has_goals_for_view = await Goal.exists_for_user(user)

        return cls(
            active=active,
            active_template=active_template,
            cache_data=cache_data,
            all_views=all_views,
            is_not_found=is_not_found,
            has_goals_for_view=has_goals_for_view,
        )

    @property
    def is_template_active(self) -> bool:
        return self.active_template is not None

    @property
    def is_view_active(self) -> bool:
        return self.active is not None

    @property
    def has_active(self) -> bool:
        return self.is_template_active or self.is_view_active

    @property
    def active_title(self) -> str | None:
        if self.active_template:
            return self.active_template.title
        if self.active:
            return self.active.title
        return None

    @property
    def active_view_request(self) -> str | None:
        if self.active_template:
            return self.active_template.view_request
        if self.active:
            return self.active.view_request
        return None

    @property
    def active_channel_id(self) -> str | None:
        if self.active_template:
            return self.active_template.to_channel_id()
        if self.active:
            return str(self.active.id)
        return None

    @property
    def cached_sections(self) -> list | None:
        return self.cache_data.sections if self.cache_data else None

    @property
    def cached_entry_ids(self) -> list[str]:
        return self.cache_data.entry_ids if self.cache_data else []

    @property
    def generating(self) -> bool:
        return self.cache_data.generating if self.cache_data else False


@dataclass
class ViewSectionPresenter:
    section: ViewSection
    goal: Goal | None
    entries: list[MailboxEntryPresenter]

    @property
    def title(self) -> str:
        return self.section.title

    @property
    def description(self) -> str:
        return self.section.description

    @classmethod
    def create(
        cls,
        section: ViewSection,
        entries_by_id: dict[str, MailboxEntryPresenter],
        goals_by_id: dict[str, Goal],
    ) -> Self:
        goal = goals_by_id.get(section.goal_id) if section.goal_id else None
        entries = [entries_by_id[eid] for eid in section.mailbox_entry_ids if eid in entries_by_id]
        return cls(section=section, goal=goal, entries=entries)

    @classmethod
    async def create_from_cache(
        cls,
        cached_sections: list[dict],
        entry_presenters: list[MailboxEntryPresenter],
    ) -> list[Self]:
        sections = [ViewSection(**section) for section in cached_sections]
        goal_ids = [section.goal_id for section in sections if section.goal_id]

        goals_by_id: dict[str, Goal] = {}
        if goal_ids:
            goals = await Goal.filter(id__in=goal_ids).prefetch_related("owner", "group", "parent")
            goals_by_id = {str(goal.id): goal for goal in goals}

        entries_by_id = {str(entry.id): entry for entry in entry_presenters}
        return [cls.create(section, entries_by_id, goals_by_id) for section in sections]
