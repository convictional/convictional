from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from sentry_sdk.ai.monitoring import ai_track
from tortoise.functions import Count
from tortoise.query_utils import Prefetch

from app.jobs.content import ContentIndexingJob
from app.jobs.notifications import Notifier
from app.models.workspaces.meetings import Meeting, MeetingCollection, MeetingJob, Transcript
from app.prompts.engine import build_prompt, organization_context
from config.enums import EventAction, JobQueue, MeetingCollectionAction
from infra.db import transaction
from infra.jobs import JobDefinition, enqueue_job, enqueue_job_in_group
from infra.messaging import Topic

#
# Completion models
#
#

LLM_TEMPERATURE: float = 0.0


class MeetingTitle(BaseModel):
    """
    Extracted title of a meeting from a transcript.
    """

    title: str = Field(..., description="The title of the meeting.")


class MeetingSummary(BaseModel):
    """
    Extracted summary of a meeting from a transcript.
    """

    summary: str = Field(..., description="The summary of the meeting.")


class MeetingDecision(BaseModel):
    decision: str = Field(..., description="The decision, stated plainly in one sentence.")
    owner: str = Field(
        ..., description='Who made or drove the decision; use "the group" when no single owner is clear.'
    )


class MeetingDecisions(BaseModel):
    """
    Decisions extracted from a meeting transcript, separately from the summary prose.
    """

    decisions: list[MeetingDecision] = Field(
        default_factory=list,
        description="Genuine decisions reached during the meeting. Empty when no decisions were made.",
    )


class MeetingAttendees(BaseModel):
    """
    Extracted list of attendees from a meeting transcript.
    """

    attendees: list[str] = Field(..., description="The names of the attendees present in the meeting.")


class MeetingCollectionSuggestion(BaseModel):
    action: MeetingCollectionAction = Field(
        ...,
        description=(
            f"One of: '{MeetingCollectionAction.EXISTING}' (suggest an existing collection),"
            f" '{MeetingCollectionAction.NEW}' (suggest creating a new collection),"
            f" or '{MeetingCollectionAction.NONE}' (no good match)."
        ),
    )
    collection_id: str | None = Field(
        None,
        description=(
            f"The ID of the existing collection to suggest."
            f" Required when action is '{MeetingCollectionAction.EXISTING}'."
        ),
    )
    collection_title: str | None = Field(
        None,
        description=(
            f"The title of the new collection to create."
            f" Required when action is '{MeetingCollectionAction.NEW}'. Keep it concise (1-4 words)."
        ),
    )


def insert_decisions_section(summary: str, decisions: list[MeetingDecision]) -> str:
    """Splice a '### Decisions' section into the summary markdown, just above the first sub-heading.

    The summary prompt produces '## Summary' followed by sub-headings ('### Key Points', etc.).
    Decisions belong right after the overview paragraph, so we insert before the first '### '. With
    no decisions we leave the summary untouched, omitting the section entirely.
    """
    if not decisions:
        return summary

    body = "\n".join(f"- {decision.decision} ({decision.owner})" for decision in decisions)
    section = f"### Decisions\n{body}"

    lines = summary.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("### "):
            return "\n".join([*lines[:index], section, "", *lines[index:]])

    return f"{summary.rstrip()}\n\n{section}\n"


#
# Jobs
#
#


class ProcessTranscriptJob(JobDefinition):
    default_queue = JobQueue.UI
    meeting_id: UUID
    should_update_title: bool = False

    @ai_track("ProcessTranscriptJob.perform")
    async def perform(self):
        meeting = await Meeting.get_or_none(id=self.meeting_id).prefetch_related("organization", "organization__users")
        if not meeting:
            return

        if not meeting.transcript:
            return

        existing_processed_transcript = (
            meeting.processed_transcript.model_copy() if meeting.processed_transcript else None
        )

        meeting.processed_transcript = Transcript.parse(meeting.transcript, meeting.creator)

        if not meeting.processed_transcript or not meeting.processed_transcript.lines:
            return

        update_fields = ["processed_transcript"]

        if meeting.processed_transcript.title:
            meeting.title = meeting.processed_transcript.title
            self.should_update_title = False
            update_fields.append("title")

        if meeting.processed_transcript.recorded_on:
            meeting.scheduled_at = datetime.combine(meeting.processed_transcript.recorded_on, datetime.min.time())
            update_fields.append("scheduled_at")

        await meeting.save(update_fields=update_fields)

        if existing_processed_transcript != meeting.processed_transcript:
            job = await enqueue_job_in_group(
                ExtractMeetingMetadataJob(
                    meeting_id=meeting.id,
                    should_update_title=self.should_update_title,
                )
            )
            await MeetingJob.create(meeting=meeting, job=job)


class ExtractMeetingMetadataJob(JobDefinition):
    default_queue = JobQueue.UI
    meeting_id: UUID
    should_update_title: bool = False

    @ai_track("ExtractMeetingMetadataJob.perform")
    async def perform(self):
        meeting = await Meeting.get_or_none(id=self.meeting_id).prefetch_related(
            "organization", "organization__users", "workspace"
        )
        if not meeting:
            return

        if not meeting.processed_transcript:
            return

        # The system prompt is identical across every extraction call, so build it once here rather
        # than re-running organization_context (a Goal query) inside each method.
        system_prompt = build_prompt(
            "extract_meeting_metadata/system.md.jinja", **(await organization_context(meeting.organization))
        )

        if self.should_update_title:
            meeting.title = await self.generate_title(meeting, system_prompt)

        if not meeting.attendees:
            speakers = await self.extract_speakers(meeting, system_prompt)
            await meeting.resolve_attendees(speakers)

        # Decisions are extracted by a dedicated, narrowly-scoped call rather than inline with the
        # summary prose, which the model was prone to over-populating. We splice them back into the
        # markdown so the stored summary keeps its single-document shape.
        summary = await self.generate_summary(meeting, system_prompt)
        decisions = await self.extract_decisions(meeting, system_prompt)
        meeting.summary = insert_decisions_section(summary, decisions)
        await meeting.save(update_fields=["title", "summary", "attendees"])

        await enqueue_job_in_group(ContentIndexingJob.from_model(meeting.organization_id, meeting))

    async def generate_title(self, meeting: Meeting, system_prompt: str):
        user_prompt = build_prompt(
            "extract_meeting_metadata/generate_title.md.jinja",
            meeting=meeting,
            users=meeting.organization.users,
        )

        title = await meeting.organization.llm.instructor_completion(
            user_prompt, system_prompt, MeetingTitle, temperature=LLM_TEMPERATURE
        )

        if not title:
            raise ValueError("Title could not be generated.")

        return title.title

    async def generate_summary(self, meeting: Meeting, system_prompt: str):
        user_prompt = build_prompt(
            "extract_meeting_metadata/generate_summary.md.jinja",
            meeting=meeting,
            users=meeting.organization.users,
        )

        summary = await meeting.organization.llm.instructor_completion(
            user_prompt, system_prompt, MeetingSummary, temperature=LLM_TEMPERATURE
        )

        if not summary:
            raise ValueError("Summary could not be generated.")

        return summary.summary

    async def extract_decisions(self, meeting: Meeting, system_prompt: str) -> list[MeetingDecision]:
        user_prompt = build_prompt(
            "extract_meeting_metadata/extract_decisions.md.jinja",
            meeting=meeting,
            users=meeting.organization.users,
        )

        result = await meeting.organization.llm.instructor_completion(
            user_prompt, system_prompt, MeetingDecisions, temperature=LLM_TEMPERATURE
        )

        # Return empty rather than raising: a failed extraction should not block the summary save.
        return result.decisions if result else []

    async def extract_speakers(self, meeting: Meeting, system_prompt: str):
        user_prompt = build_prompt(
            "extract_meeting_metadata/extract_speakers.md.jinja",
            meeting=meeting,
            users=meeting.organization.users,
        )

        speakers = await meeting.organization.llm.instructor_completion(
            user_prompt,
            system_prompt,
            MeetingAttendees,
            temperature=LLM_TEMPERATURE,
        )

        return speakers.attendees


#
# Post-processing
#
#


class MeetingProcessingCompleteCallbackJob(JobDefinition):
    default_queue = JobQueue.UI
    meeting_id: UUID

    @ai_track("MeetingProcessingCompleteCallbackJob.perform")
    async def perform(self):
        meeting = await Meeting.get_or_none(id=self.meeting_id).prefetch_related("workspace")
        if not meeting:
            return

        if not meeting.processed_transcript or not meeting.summary:
            return

        async with Notifier(meeting).record_and_notify(EventAction.MEETING_PROCESSED):
            pass

        await Topic("meeting_bot", meeting_id=meeting.id).broadcast()

        if meeting.collection_id is None:
            await enqueue_job(AssignMeetingCollectionJob(meeting_id=meeting.id))


class AssignMeetingCollectionJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    meeting_id: UUID

    @ai_track("AssignMeetingCollectionJob.perform")
    async def perform(self):
        meeting = await Meeting.get_or_none(id=self.meeting_id).prefetch_related("organization", "workspace")
        if not meeting or meeting.collection_id is not None:
            return

        collections = (
            await MeetingCollection.filter(organization_id=meeting.organization_id)
            .annotate(meeting_count=Count("meetings_collection"))
            .prefetch_related(
                Prefetch(
                    "meetings_collection",
                    queryset=Meeting.all().order_by("-scheduled_at"),
                )
            )
            .order_by("title")
        )
        for collection in collections:
            collection.sample_meeting_titles = [m.title for m in collection.meetings_collection[:5]]  # type: ignore[attr-defined]

        system_prompt = build_prompt(
            "extract_meeting_metadata/system.md.jinja", **(await organization_context(meeting.organization))
        )

        user_prompt = build_prompt(
            "meetings/suggest_collection.md.jinja",
            meeting=meeting,
            collections=collections,
            actions=MeetingCollectionAction,
        )

        suggestion = await meeting.organization.llm.instructor_completion(
            user_prompt, system_prompt, MeetingCollectionSuggestion, temperature=LLM_TEMPERATURE
        )

        if suggestion.action == MeetingCollectionAction.EXISTING and suggestion.collection_id:
            suggested_id = UUID(suggestion.collection_id)
            matched = next((c for c in collections if c.id == suggested_id), None)
            if matched:
                async with transaction() as connection:
                    await meeting.assign_collection(
                        matched, meeting.creator_id, using_db=connection, auto_assigned=True
                    )
        elif suggestion.action == MeetingCollectionAction.NEW and suggestion.collection_title:
            async with transaction() as connection:
                collection = await MeetingCollection.create(
                    organization_id=meeting.organization_id,
                    title=suggestion.collection_title,
                    using_db=connection,
                )
                await meeting.assign_collection(
                    collection, meeting.creator_id, using_db=connection, auto_assigned=True
                )
