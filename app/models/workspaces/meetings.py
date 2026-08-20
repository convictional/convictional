import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Self
from uuid import UUID

import webvtt  # type: ignore
import webvtt.errors  # type: ignore
from pydantic import BaseModel, Field
from tortoise import BaseDBAsyncClient, fields
from tortoise.expressions import Q
from tortoise.signals import post_save
from tortoise.transactions import atomic

from app.models.accounts import Organization, User
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.workspace import (
    CollaborationPolicy,
    Collaborator,
    Workspace,
    WorkspaceMixin,
    WorkspaceMixinFilters,
)
from config import settings
from config.enums import EventAction, MeetingAttendeeStatus, MeetingChatMessageSenderPlatform, Sharing
from infra.db import PartialIndex, PydanticField, PydanticListField, RecordModel
from infra.jobs import Job
from infra.messaging import Topic
from infra.storage import FileReference
from lib.encoding import LLM_ENCODING, chunk_objects
from lib.json import JSONDumps


@dataclass
class MeetingCollaborationPolicy(CollaborationPolicy):
    meeting: "Meeting"

    def can_be_accessed_by(self, user: User):
        if self.meeting.creator_id == user.id:
            return True

        return super().can_be_accessed_by(user)

    def is_removable(self, user_id: UUID):
        return user_id not in [a.user_id for a in self.meeting.resolved_attendees]


class MeetingChatMessageSender(BaseModel):
    id: int | None = Field(default=None)  # matches meeting_participants.id in the RecallAIBot object
    name: str
    is_host: bool | None = Field(default=None)
    platform: MeetingChatMessageSenderPlatform | None = Field(default=None)
    extra_detail: dict[str, Any] | None = Field(default=None)


class MeetingChatMessage(BaseModel):
    text: str
    created_at: str | datetime
    to: str
    sender: MeetingChatMessageSender


class MeetingAttendee(BaseModel):
    user_id: UUID | None = None
    name: str | None = None
    status: MeetingAttendeeStatus | None = None
    is_organizer: bool = False

    @property
    def display_name(self):
        return self.name


class TranscriptLine(BaseModel):
    line_number: int
    speaker: str | None
    content: str
    start_time: float | None = None
    end_time: float | None = None

    def __str__(self):
        return f"{self.speaker}: {self.content}" if self.speaker else self.content


class TranscriptChunk(BaseModel):
    lines: list[TranscriptLine]

    @property
    def first_line_number(self):
        return self.lines[0].line_number

    @property
    def last_line_number(self):
        return self.lines[-1].line_number

    def __str__(self):
        return "\n".join([str(line) for line in self.lines])


class Transcript(BaseModel):
    title: str | None = None  # Some transcripts encode a title
    recorded_on: date | None = None  # Some transcripts encode a date

    lines: list[TranscriptLine]

    def __str__(self):
        return "\n".join([str(line) for line in self.lines]) + "\n"

    @classmethod
    def parse(cls, transcript: str, user: User | None = None):
        parser = get_correct_transcript_parser(transcript)
        if parser:
            return parser.parse(transcript, user)

        return cls._parse_lines(transcript)

    @classmethod
    def _parse_lines(cls, transcript: str):
        parsed_lines: list[TranscriptLine] = []
        for i, line in enumerate(transcript.splitlines()):
            line_split_by_colon = line.split(": ", 1)
            if len(line_split_by_colon) < 2:
                parsed_lines.append(TranscriptLine(line_number=i, speaker="", content=line.strip()))
                continue

            speaker, content = line_split_by_colon
            parsed_lines.append(TranscriptLine(line_number=i, speaker=speaker.strip(), content=content.strip()))

        return cls(lines=parsed_lines)

    def chunked(self, target_tokens_per_chunk: int = 8096) -> Iterable[TranscriptChunk]:
        """
        Chunks the meeting's transcript into chunks that are roughly equal in token length.
        """

        for chunk in chunk_objects(self.lines, lambda line: str(line), target_tokens_per_chunk, encoding=LLM_ENCODING):
            yield TranscriptChunk(lines=chunk)

    def lines_by_line_numbers(self, line_numbers: list[int]):
        return [line for line in self.lines if line.line_number in line_numbers]


class TranscriptParser:
    @classmethod
    def parse(cls, transcript: str, user: User | None = None) -> Transcript:
        raise NotImplementedError("This method should be implemented by subclasses")

    @classmethod
    def is_correct_parser(cls, transcript: str) -> bool:
        raise NotImplementedError("This method should be implemented by subclasses")


class WebVTTTranscriptParser(TranscriptParser):
    @classmethod
    def is_correct_parser(cls, transcript: str) -> bool:
        try:
            webvtt.from_string(transcript)
        except webvtt.errors.MalformedFileError:
            return False

        return True

    @classmethod
    def parse(cls, transcript: str, user: User | None = None) -> Transcript:
        webvtt_transcript = webvtt.from_string(transcript)

        parsed_lines: list[TranscriptLine] = []
        for i, caption in enumerate(webvtt_transcript.captions):
            # WebVTT Transcripts have a dedicated location for the speaker
            speaker = caption.voice
            content = caption.text.strip()
            if not speaker:
                # However, it's not always used.
                try:
                    maybe_speaker, maybe_content = caption.text.split(":", 1)
                    speaker = maybe_speaker.strip()
                    content = maybe_content.strip()
                except ValueError:
                    pass

            # Append the content to the previous line if it's the same speaker
            if parsed_lines and parsed_lines[-1].speaker == speaker:
                parsed_lines[-1].content += f" {content}"
                continue

            parsed_lines.append(
                TranscriptLine(
                    line_number=i,
                    speaker=speaker,
                    content=content,
                )
            )

        return Transcript(lines=parsed_lines)


class RTFTranscriptParser(TranscriptParser):
    @classmethod
    def is_correct_parser(cls, transcript: str) -> bool:
        first_line = transcript.split("\n", maxsplit=1)[0].strip()
        is_rtf = first_line.startswith("{\\rtf")
        return is_rtf

    @classmethod
    def parse(cls, transcript: str, user: User | None = None) -> Transcript:
        # Remove RTF formatting
        transcript = re.sub(r"{\\[^}]+}", "", transcript)  # Remove RTF header and footer
        transcript = re.sub(r"\\[a-z]+\d*", "", transcript)  # Remove RTF control words
        transcript = re.sub(r"\\\S+", "", transcript)  # Remove any other control symbols
        transcript = re.sub(r"\s{2,}", " ", transcript)  # Replace multiple spaces with a single space
        transcript = transcript.replace("\\", "")  # Remove any remaining backslashes
        transcript = transcript.replace("}", "").replace("{", "")  # Remove braces

        return Transcript.parse(transcript, user)


PREFERRED_TRANSCRIPT_PARSER_ORDER = ["recall", "webvtt", "rtf", "fathom", "granola"]
TranscriptParserClass = type[TranscriptParser]
transcript_parser_registry: dict[str, TranscriptParserClass] = {
    "webvtt": WebVTTTranscriptParser,
    "rtf": RTFTranscriptParser,
}


def register_transcript_parser(name: str, parser: TranscriptParserClass):
    transcript_parser_registry[name] = parser


def get_correct_transcript_parser(transcript: str) -> TranscriptParserClass | None:
    parsers_in_order = [parser for parser in PREFERRED_TRANSCRIPT_PARSER_ORDER if parser in transcript_parser_registry]
    parsers_in_order.extend(
        [parser_name for parser_name in transcript_parser_registry if parser_name not in parsers_in_order]
    )

    for parser_name in parsers_in_order:
        if transcript_parser_registry[parser_name].is_correct_parser(transcript):
            return transcript_parser_registry[parser_name]
    return None


class MeetingCollection(RecordModel):
    title = fields.TextField()
    description: str | None = fields.TextField(null=True)
    organization_id: Annotated[UUID, "foreign key to organization"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")

    class Meta:
        ordering = ["title"]
        indexes = (("organization_id",),)


class MeetingFilters(WorkspaceMixinFilters):
    @classmethod
    def by_not_started(cls) -> Q:
        return Q(scheduled_at__gt=datetime.now(UTC))

    @classmethod
    def by_organization_or_user(cls, organization_id: UUID, user_id: UUID):
        return Q(organization_id=organization_id) & cls.by_user_access(user_id)

    @classmethod
    def by_user_access(cls, user_id: UUID):
        return Q(sharing=Sharing.ORGANIZATION) | Q(creator_id=user_id) | cls.by_collaborated_workspaces(user_id)

    @classmethod
    def by_creator_or_collaborator(cls, user_id: UUID):
        return Q(creator_id=user_id) | cls.by_collaborated_workspaces(user_id)

    @classmethod
    def by_future(cls, end_date: datetime | None = None):
        scheduled_after_now = Q(scheduled_end_at__gt=datetime.now(UTC))
        if end_date:
            return scheduled_after_now & Q(scheduled_end_at__lt=end_date)
        return scheduled_after_now

    @classmethod
    def by_scheduled_today_and_future(cls, start_of_today):
        # Note: start_of_today should be localized to the user's timezone
        return Q(scheduled_at__gte=start_of_today)

    @classmethod
    def by_scheduled_between(cls, start: datetime, end: datetime):
        return Q(scheduled_at__gte=start) & Q(scheduled_at__lt=end)

    @classmethod
    def by_not_completed(cls):
        # Mirror of Meeting.is_completed: has no transcript, and either ends in the future
        # or (end unset) started within the last hour.
        now = datetime.now(UTC)
        return Q(transcript__isnull=True) & (
            Q(scheduled_end_at__gte=now)
            | (Q(scheduled_end_at__isnull=True) & Q(scheduled_at__gte=now - timedelta(hours=1)))
        )

    @classmethod
    def by_completed(cls):
        # Inverse of by_not_completed: has a transcript, or has ended, or (no end set)
        # started more than an hour ago. Mirrors Meeting.is_completed.
        now = datetime.now(UTC)
        return (
            Q(transcript__isnull=False)
            | (Q(scheduled_end_at__isnull=False) & Q(scheduled_end_at__lt=now))
            | (Q(scheduled_end_at__isnull=True) & Q(scheduled_at__lt=now - timedelta(hours=1)))
        )

    @classmethod
    def by_past(cls):
        return Q(scheduled_end_at__lt=datetime.now(UTC)) | (Q(scheduled_end_at__isnull=True) & cls.by_has_transcript())

    @classmethod
    def by_collection(cls, collection_id: UUID):
        return Q(collection_id=collection_id)

    @classmethod
    def by_uncategorized(cls):
        return Q(collection_id__isnull=True)

    @classmethod
    def by_not_declined_by(cls, user_id: UUID):
        # `attendees` is a JSONB column whose UUIDs are stored in the project's
        # tagged form ({"__uuid__": true, "value": ...}). Build the containment
        # operand through the same encoder (JSONDumps) so it stays in sync with
        # the stored shape if that encoding ever changes, then exclude meetings
        # whose array contains an element marking this user as declined (Postgres
        # `@>` via Tortoise's `contains` lookup). Filtering in the query — rather
        # than dropping declined rows after pagination — keeps page sizes full
        # and `has_more` honest. Meetings where the user isn't an attendee, or
        # hasn't declined, are kept.
        #
        # Note: this is a *negated* containment (`NOT (attendees @> ...)`). A GIN
        # index on `attendees` only accelerates the positive `@>` test, so it
        # would not help here; the predicate is evaluated against the rows the
        # `organization_id`/`creator_id` indexes already narrow the scan to.
        declined = json.loads(JSONDumps([{"user_id": user_id, "status": MeetingAttendeeStatus.DECLINED.value}]))
        return ~Q(attendees__contains=declined)

    @classmethod
    def by_ical_uid(cls, ical_uid: str):
        return Q(ical_uid=ical_uid)

    @classmethod
    def by_provider_meeting_id(cls, provider_meeting_id: str | None):
        if not provider_meeting_id:
            # Mypy guard, we should be checking for a valid provider_meeting_id before using this filter
            raise ValueError("provider_meeting_id must be provided")
        return Q(provider_meeting_id=provider_meeting_id)

    @classmethod
    def by_has_transcript(cls):
        return Q(transcript__isnull=False)


class Meeting(WorkspaceMixin, RecordModel):
    scheduled_at: datetime | None = fields.DatetimeField(null=True)
    scheduled_end_at: datetime | None = fields.DatetimeField(null=True)
    summary: str | None = fields.TextField(null=True)
    organizer: MeetingAttendee | None = PydanticField(pydantic_model=MeetingAttendee, null=True)  # type: ignore
    attendees: list[MeetingAttendee] = PydanticListField(pydantic_model=MeetingAttendee, default=[])
    transcript: str | None = fields.TextField(null=True)
    processed_transcript: Transcript | None = PydanticField(pydantic_model=Transcript, null=True)  # type: ignore
    chat_messages: list[MeetingChatMessage] = PydanticListField(pydantic_model=MeetingChatMessage, default=[])
    ical_uid: str | None = fields.TextField(null=True)
    provider_meeting_id: str | None = fields.TextField(null=True)
    count_occurrences: int = fields.IntField(default=1)
    conferencing_url: str | None = fields.TextField(null=True)
    agenda = fields.TextField(null=True)
    manually_created_at: datetime | None = fields.DatetimeField(null=True)
    did_recording_fail = fields.BooleanField(default=False)

    # Relationships
    recording: fields.ForeignKeyNullableRelation[FileReference] = fields.ForeignKeyField(
        "convictional.FileReference", related_name="meeting_recordings", null=True
    )
    recording_id: Annotated[UUID | None, "foreign key to file"]
    collection: fields.ForeignKeyNullableRelation[MeetingCollection] = fields.ForeignKeyField(
        "convictional.MeetingCollection", related_name="meetings_collection", null=True, on_delete=fields.SET_NULL
    )
    collection_id: Annotated[UUID | None, "foreign key to collection"]
    collection_auto_assigned = fields.BooleanField(default=False)
    jobs: fields.ReverseRelation["MeetingJob"]
    filters = MeetingFilters()

    class Meta:
        ordering = ["-scheduled_at"]
        indexes = (
            ("scheduled_at",),
            PartialIndex(fields=["provider_meeting_id", "scheduled_at"], extra="deleted_at IS NULL"),
            PartialIndex(fields=["organization_id", "sharing", "creator_id"], extra="deleted_at IS NULL"),
        )

    def __str__(self):
        s = f"# {self.title}\n\n"

        if self.scheduled_at:
            s = s + f"*{self.scheduled_at}*\n\n"
        if self.processed_transcript:
            s = s + str(self.processed_transcript)

        return s

    def __repr__(self):
        excluded_fields = ["transcript", "chat_messages", "processed_transcript", "summary"]
        field_values = ", ".join(
            [f"{field}={getattr(self, field)}" for field in self._meta.fields_map if field not in excluded_fields]
        )
        return f"<{self.__class__.__name__} {field_values}>"

    async def assign_collection(
        self,
        collection: "MeetingCollection",
        current_user_id: UUID,
        using_db: BaseDBAsyncClient,
        auto_assigned: bool = False,
    ):
        """Assign a collection to this meeting and all other instances of the same recurring meeting."""
        self.collection_id = collection.id
        self.collection_auto_assigned = auto_assigned
        async with self.workspace.record(
            EventAction.MEETING_UPDATED, creator_id=current_user_id, using_db=using_db
        ) as recording:
            recording.event.details.update({"collection_title": collection.title})
            await self.save(using_db=using_db)

        if self.ical_uid is not None:
            other_instances = (
                await Meeting.filter(ical_uid=self.ical_uid, organization_id=self.organization_id)
                .exclude(id=self.id)
                .using_db(using_db)
                .prefetch_related("workspace")
                .all()
            )
            for instance in other_instances:
                instance.collection_id = collection.id
                instance.collection_auto_assigned = auto_assigned
                async with instance.workspace.record(
                    EventAction.MEETING_UPDATED, creator_id=current_user_id, using_db=using_db
                ) as recording:
                    recording.event.details.update({"collection_title": collection.title})
                    await instance.save(using_db=using_db)

    async def unassign_collection(
        self,
        current_user_id: UUID,
        using_db: BaseDBAsyncClient,
    ):
        """Clear the collection from this meeting only.

        Asymmetric with ``assign_collection`` by design: assigning fans out to every
        instance of a recurring meeting, but unassigning a single instance does not —
        callers may want to pull just one occurrence out of a series.
        """
        self.collection_id = None
        self.collection_auto_assigned = False
        async with self.workspace.record(
            EventAction.MEETING_UPDATED, creator_id=current_user_id, using_db=using_db
        ) as recording:
            recording.event.details.update({"collection_title": "Uncategorized"})
            await self.save(using_db=using_db)

    @staticmethod
    def is_valid_conferencing_url(url: str) -> bool:
        """
        Validates if a URL is from a supported conferencing platform: Zoom, Google Meet, or MS Teams.
        Returns True if the URL is valid, False otherwise.
        """
        if not url or not isinstance(url, str):
            return False

        url = url.strip()
        if not url:
            return False

        # Zoom patterns
        zoom_patterns = [
            r"^https://.*\.zoom\.us/j/\d+",
            r"^https://zoom\.us/j/\d+",
            r"^https://.*\.zoom\.us/my/",
            r"^https://zoom\.us/my/",
        ]

        # Google Meet patterns
        google_meet_patterns = [
            r"^https://meet\.google\.com/[a-z0-9-]+",
        ]

        # MS Teams patterns (based on recall.ai regexes)
        teams_patterns = [
            # teams_regex_one
            r"^http.+meetup-join/(?P<thread_id>.+)/(?P<message_id>[0-9]+)\?context=(?P<context>\{.+\})&?",
            # teams_regex_two
            r"^http.+message/(?P<thread_id>.+)/(?P<message_id>[0-9]+)\?(?P<query>[^<\s.]+)",
            # teams_regex_three
            r"^http.+meetup-join/(?P<thread_id>.+)/(?P<message_id>[0-9]+)\?context=(?P<context>[^& ]+)",
            # teams_regex_four - personal meeting invite
            r'^https://teams\.live\.com/meet/(?P<meeting_id>[0-9]+)((.*)p=(?P<meeting_password>[^&#,<"\n >]+))?',
            # teams_regex_five - short business meeting invite
            r'^https://teams\.microsoft\.com/meet/(?P<meeting_id>[0-9]+)((.*)p=(?P<meeting_password>[^&#,<"\n >]+))?',
        ]

        all_patterns = zoom_patterns + google_meet_patterns + teams_patterns

        for pattern in all_patterns:
            if re.match(pattern, url, re.VERBOSE):
                return True

        return False

    @classmethod
    def by_organization_or_user(cls, organization_id: UUID, user_id: UUID):
        return cls.filter(cls.filters.by_organization_or_user(organization_id, user_id))

    @classmethod
    def by_user(cls, organization_id: UUID, user_id: UUID):
        return cls.filter(Q(organization_id=organization_id) & cls.filters.by_creator_or_collaborator(user_id))

    @property
    def duration(self):
        if self.scheduled_at and self.scheduled_end_at:
            return self.scheduled_end_at - self.scheduled_at
        return None

    @property
    def is_joinable_by_recall(self):
        return bool(
            self.conferencing_url
            and any([d for d in settings.recall_ai_providers.values() if d in self.conferencing_url])
            and self.scheduled_at
        )

    @property
    def is_scheduled(self):
        return self.scheduled_at is not None

    @property
    def is_completed(self):
        if self.transcript:
            return True

        current_time = datetime.now(UTC)

        if self.scheduled_end_at:
            return self.scheduled_end_at < current_time

        # If the meeting doesn't have an end time, we consider it completed if it started more than an hour ago
        if self.scheduled_at:
            return self.scheduled_at < current_time - timedelta(hours=1)

        return False

    @property
    def is_future(self):
        current_time = datetime.now(UTC)
        return self.scheduled_at and self.scheduled_at > current_time

    @property
    def is_happening_now(self):
        current_time = datetime.now(UTC)

        if self.scheduled_at and self.scheduled_end_at:
            return self.scheduled_at <= current_time <= self.scheduled_end_at

        return (
            self.scheduled_at
            and self.scheduled_at > current_time - timedelta(hours=1)
            and self.scheduled_at < current_time
            and not self.transcript
        )

    @property
    def is_upcoming(self):
        return self.is_future or self.is_happening_now

    @property
    def unresolved_attendees(self):
        return [a for a in self.attendees if not a.user_id]

    @property
    def resolved_attendees(self):
        return [a for a in self.attendees if a.user_id]

    @property
    def has_provider_meeting_id(self):
        return bool(self.provider_meeting_id)

    @property
    def is_recurring(self):
        return self.count_occurrences > 1

    @property
    def conferencing_provider(self) -> str | None:
        if not self.conferencing_url:
            return None

        for provider, url_substr in settings.recall_ai_providers.items():
            if url_substr in self.conferencing_url:
                return provider

        return None

    @property
    def busy_jobs(self):
        return [job.job for job in self.jobs if not job.job.is_completed_or_dead]

    @property
    def is_internal(self):
        return len(self.unresolved_attendees) == 0

    @property
    def agenda_topic(self):
        return Topic("meeting_agenda", meeting_id=self.id)

    @property
    def agenda_document(self):
        return LiveDocument.for_topic(self.agenda_topic)

    async def has_agenda(self) -> bool:
        if self.agenda and self.agenda.strip():
            return True

        live_document = await self.agenda_document
        return bool(live_document.markdown.strip())

    async def get_agenda_markdown(self) -> str:
        """Get the current markdown content from the live document."""
        live_document = await self.agenda_document
        return live_document.markdown or ""

    @property
    def collaboration(self) -> MeetingCollaborationPolicy:
        return MeetingCollaborationPolicy(workspace=self.workspace, meeting=self)

    async def get_previous_meeting(self, using_db: BaseDBAsyncClient | None = None) -> Self | None:
        if not self.has_provider_meeting_id:
            return None

        previous_meeting = (
            await self.filter(Meeting.filters.by_provider_meeting_id(self.provider_meeting_id))
            .filter(scheduled_at__lt=self.scheduled_at)
            .using_db(using_db)
            .first()
        )
        return previous_meeting

    async def get_next_meeting(self) -> Self | None:
        """
        Returns the next meeting in the series, if it has already happened or is in-progress.
        Excludes meetings that haven't started yet.
        """
        if not self.has_provider_meeting_id:
            return None

        next_meeting = (
            await self.filter(Meeting.filters.by_provider_meeting_id(self.provider_meeting_id))
            .filter(scheduled_at__gt=self.scheduled_at)
            .exclude(Meeting.filters.by_not_started())
            .order_by("scheduled_at")
            .first()
        )
        return next_meeting

    async def resolve_attendees(self, speakers: list[str]):
        results: list[MeetingAttendee] = []
        users = await self.organization.users.all()

        for name in speakers:
            existing_user = next((user for user in users if user.display_name.lower() == name.lower()), None)
            if existing_user:
                results.append(MeetingAttendee(user_id=existing_user.id, name=existing_user.display_name))

            results.append(MeetingAttendee(name=name))

        self.attendees = results

    async def add_attendee(self, attendee: MeetingAttendee) -> MeetingAttendee:
        if attendee not in self.attendees:
            self.attendees.append(attendee)

        return attendee

    def get_attendee_by_name(self, name: str):
        return next(
            (attendee for attendee in self.attendees if attendee.name and attendee.name.lower() == name.lower()), None
        )

    def get_attendee_by_user_id(self, user_id: UUID):
        return next((attendee for attendee in self.attendees if attendee.user_id == user_id), None)

    def ensure_internal_organizer_is_creator(self):
        # If the organizer is an internal user, set them as the creator of the meeting if they are not already the
        # creator. This is necessary because we process calendar events by user and the creator of the meeting may not
        # be the user that we first checked the event for.
        if self.organizer and self.organizer.user_id:
            if self.creator_id != self.organizer.user_id:
                self.creator_id = self.organizer.user_id


@atomic("default")
@post_save(Meeting)
async def ensure_attendee_collaborators(
    sender: "type[Meeting]", instance: Meeting, created: bool, using_db: BaseDBAsyncClient, update_fields: list[str]
) -> None:
    if not isinstance(instance.workspace, Workspace):
        await instance.fetch_related("workspace", using_db=using_db)

    for attendee in instance.attendees:
        if attendee.user_id:
            await Collaborator.get_or_create(
                workspace_id=instance.workspace_id, user_id=attendee.user_id, using_db=using_db
            )


@atomic("default")
@post_save(Meeting)
async def update_count_recurrence(
    sender: "type[Meeting]", instance: Meeting, created: bool, using_db: BaseDBAsyncClient, update_fields: list[str]
) -> None:
    if not created:
        return

    if not instance.has_provider_meeting_id:
        return

    filter_condition = Meeting.filters.by_provider_meeting_id(
        instance.provider_meeting_id
    ) & Meeting.filters.by_organization(instance.organization_id)

    count_recurrence = await sender.filter(filter_condition).count()

    if count_recurrence == 1:
        return

    await sender.filter(filter_condition).using_db(using_db).update(count_occurrences=count_recurrence)


class MeetingJob(RecordModel):
    meeting: fields.ForeignKeyRelation[Meeting] = fields.ForeignKeyField("convictional.Meeting", related_name="jobs")
    meeting_id: Annotated[UUID, "foreign key to meeting"]
    job: fields.ForeignKeyRelation[Job] = fields.ForeignKeyField("convictional.Job", related_name="meeting_jobs")
    job_id: Annotated[UUID, "foreign key to job"]

    class Meta:
        ordering = ["-created_at"]
        indexes = (("meeting_id",), ("job_id",))
