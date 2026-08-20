from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.jobs.meetings import (
    ExtractMeetingMetadataJob,
    MeetingProcessingCompleteCallbackJob,
    ProcessTranscriptJob,
)
from app.jobs.notifications import Notifier
from app.models.accounts import User
from app.models.workspaces.meetings import Meeting, MeetingCollection, MeetingJob
from app.presenters.meeting import MeetingSummaryPresenter
from app.routers.api.schemas import PaginatedResponse, UserResponse
from app.routers.api.serializers import user_response
from app.routers.api.streams import register_live_document_handler
from app.routers.dependencies import (
    Helpers,
    get_current_user,
    get_helpers,
    get_meeting,
    index_meeting,
)
from config.enums import EventAction, MeetingAttendeeStatus, Sharing
from infra.db import Pagination, transaction
from infra.jobs import enqueue_job_group
from infra.storage import FileReference

router = APIRouter(dependencies=[Depends(index_meeting, scope="function")], tags=["meetings"])

# v4 signed-POST policies cap a single object at 5 GiB; recordings well under that.
MAX_RECORDING_BYTES = 5 * 1024 * 1024 * 1024


class AttendeeStatusResponse(BaseModel):
    display_name: str | None
    status: str | None


class MeetingCollectionResponse(BaseModel):
    id: str
    title: str
    auto_assigned: bool


class TranscriptLineResponse(BaseModel):
    line_number: int
    speaker: str | None
    content: str
    start_time: float | None
    end_time: float | None


class ProcessedTranscriptResponse(BaseModel):
    lines: list[TranscriptLineResponse]


# Nullable fields (`scheduled_at`, `collection_id`) use ``model_fields_set`` in the
# handler to distinguish "absent" (leave untouched) from "explicit null" (clear).
# Non-nullable text fields stick with the ``is not None`` idiom — they aren't
# clearable via PATCH and `null` isn't a meaningful payload.
# `recording_key` is set-only — clients read `recording_id` from the response.
class UpdateMeetingRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    agenda: str | None = None
    scheduled_at: datetime | None = None
    collection_id: UUID | None = None
    recording_key: str | None = None
    sharing: Sharing | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("must set at least one field")
        return self


class MeetingRecordingResponse(BaseModel):
    id: str
    url: str


# Signed direct-upload target the client POSTs the recording to, then echoes
# `key` back via PATCH recording_key. `fields` are opaque form fields (signature,
# policy, Content-Type, …) the client must include verbatim alongside the file.
class RecordingUploadTargetResponse(BaseModel):
    action: str
    fields: dict[str, str]
    key: str


# Recall.ai in-meeting chat (Zoom/Meet/Teams chat captured by the bot). The
# source MeetingChatMessage.sender carries a Recall participant id (int, not a
# Convictional user id); we flatten it to just the display name here to keep the API
# decoupled from Recall's internal numbering.
class MeetingChatMessageResponse(BaseModel):
    sender_name: str
    text: str
    created_at: datetime


class MeetingChatListResponse(PaginatedResponse):
    messages: list[MeetingChatMessageResponse]


# Single shape shared by the show route and every list/mutation endpoint.
# Keeping one MeetingResponse means callers only ever destructure one shape,
# and adding a field for the show view automatically broadens what list rows
# can render without per-row show fetches. The cost is that list endpoints
# pay the same prefetch + per-row build cost as show.
class MeetingResponse(BaseModel):
    id: str
    title: str | None
    summary: str | None
    agenda: str | None

    scheduled_at: datetime | None
    scheduled_end_at: datetime | None
    is_completed: bool
    is_upcoming: bool
    is_happening_now: bool
    is_recurring: bool
    # Whether the meeting has a text or collaborative (live-document) agenda.
    has_agenda: bool
    # Declined by the requesting user. Drives the struck-through upcoming row.
    is_declined: bool
    is_initial_processing: bool
    is_deleted: bool
    did_recording_fail: bool
    # Presence of a raw transcript, which decides processing vs. ready.
    has_transcript: bool
    # Whether any in-meeting chat exists, so the client can disable the Chat tab
    # up front instead of after a fetch.
    has_chat_messages: bool

    source_url: str
    workspace_id: str
    sharing: str

    recording_id: str | None

    conferencing_url: str | None

    user_attendees: list[UserResponse]
    unresolved_attendees: list[AttendeeStatusResponse]

    collection: MeetingCollectionResponse | None
    previous_meeting_id: str | None
    next_meeting_id: str | None
    next_meeting_scheduled_at: datetime | None


class MeetingListResponse(PaginatedResponse):
    meetings: list[MeetingResponse]


def _is_initial_processing(meeting: Meeting) -> bool:
    return any(
        isinstance(job.job_definition, (ExtractMeetingMetadataJob, ProcessTranscriptJob)) for job in meeting.busy_jobs
    )


def _meeting_collection_response(meeting: Meeting) -> MeetingCollectionResponse | None:
    if not meeting.collection:
        return None
    return MeetingCollectionResponse(
        id=str(meeting.collection.id),
        title=meeting.collection.title,
        auto_assigned=meeting.collection_auto_assigned,
    )


def _processed_transcript_response(meeting: Meeting) -> ProcessedTranscriptResponse | None:
    if not meeting.processed_transcript:
        return None
    return ProcessedTranscriptResponse(
        lines=[
            TranscriptLineResponse(
                line_number=line.line_number,
                speaker=line.speaker,
                content=line.content,
                start_time=line.start_time,
                end_time=line.end_time,
            )
            for line in meeting.processed_transcript.lines
        ],
    )


async def _meeting_response(
    meeting: Meeting,
    *,
    current_user_id: UUID,
    for_list_view: bool = False,
    users_by_id: dict[UUID, User] | None = None,
    has_agenda: bool | None = None,
) -> MeetingResponse:
    resolved_attendee_ids = [a.user_id for a in meeting.attendees if a.user_id]
    # List callers pass a page-wide `users_by_id` so a 25-row page resolves
    # attendees in one query instead of one per row. Single-meeting callers
    # leave it None and we resolve just this meeting's attendees here.
    if users_by_id is None:
        users_by_id = {}
        if resolved_attendee_ids:
            users = await User.filter(
                id__in=resolved_attendee_ids,
                organization_id=meeting.organization_id,
            )
            users_by_id = {u.id: u for u in users}

    # An attendee with a `user_id` that doesn't resolve to a same-org User
    # (a deleted or cross-org attendee) falls back to its embedded display_name
    # rather than being dropped, so every attendee is still counted and named —
    # matching the legacy `attendees|length` / name list.
    user_attendees: list[UserResponse] = []
    unresolved_attendees: list[AttendeeStatusResponse] = []
    for attendee in meeting.attendees:
        serialized = user_response(users_by_id.get(attendee.user_id)) if attendee.user_id else None
        if serialized:
            user_attendees.append(serialized)
        else:
            unresolved_attendees.append(
                AttendeeStatusResponse(
                    display_name=attendee.display_name,
                    status=attendee.status.value if attendee.status else None,
                )
            )

    # for_list_view skips the per-row Y-doc agenda fetch and the recurring-series
    # neighbor lookups so a 25-row list doesn't pay 25× show-only round-trips.
    previous_meeting = None
    next_meeting = None
    if not for_list_view and meeting.is_recurring:
        previous_meeting = await meeting.get_previous_meeting()
        next_meeting = await meeting.get_next_meeting()

    agenda_markdown = "" if for_list_view else await meeting.get_agenda_markdown()
    # List callers pass a batched `has_agenda` (one LiveDocumentUpdate lookup for
    # the whole page) so the agenda indicator survives the per-row Y-doc skip
    # above; single-meeting callers compute it directly.
    if has_agenda is None:
        has_agenda = await meeting.has_agenda()

    is_declined = any(
        a.user_id == current_user_id and a.status == MeetingAttendeeStatus.DECLINED for a in meeting.attendees
    )

    return MeetingResponse(
        id=str(meeting.id),
        title=meeting.title,
        summary=meeting.summary,
        agenda=agenda_markdown,
        scheduled_at=meeting.scheduled_at,
        scheduled_end_at=meeting.scheduled_end_at,
        is_completed=meeting.is_completed,
        is_upcoming=bool(meeting.is_upcoming),
        is_happening_now=bool(meeting.is_happening_now),
        is_recurring=meeting.is_recurring,
        has_agenda=has_agenda,
        is_declined=is_declined,
        is_initial_processing=_is_initial_processing(meeting),
        is_deleted=meeting.is_deleted,
        did_recording_fail=meeting.did_recording_fail,
        has_transcript=bool(meeting.transcript),
        has_chat_messages=bool(meeting.chat_messages),
        source_url=f"/meetings/{meeting.id}",
        workspace_id=str(meeting.workspace_id),
        sharing=meeting.sharing.value,
        recording_id=str(meeting.recording_id) if meeting.recording_id else None,
        conferencing_url=meeting.conferencing_url,
        user_attendees=user_attendees,
        unresolved_attendees=unresolved_attendees,
        collection=_meeting_collection_response(meeting),
        previous_meeting_id=str(previous_meeting.id) if previous_meeting else None,
        next_meeting_id=str(next_meeting.id) if next_meeting else None,
        next_meeting_scheduled_at=next_meeting.scheduled_at if next_meeting else None,
    )


async def _fetch_meeting_response(meeting_id: UUID, current_user_id: UUID) -> MeetingResponse:
    meeting = await Meeting.get(id=meeting_id).prefetch_related(
        "organization", "workspace__collaborators__user", "jobs__job", "recording", "collection"
    )
    return await _meeting_response(meeting, current_user_id=current_user_id)


async def _meeting_list_responses(
    meetings: list[Meeting], *, current_user_id: UUID, organization_id: UUID
) -> list[MeetingResponse]:
    """Build list-view responses for a page of meetings with page-wide batching.

    Resolves attendee users in a single query and the agenda signal in one
    LiveDocumentUpdate lookup, so a 25-row page doesn't pay 25× per-row IO.
    """
    attendee_ids = {a.user_id for meeting in meetings for a in meeting.attendees if a.user_id}
    users_by_id: dict[UUID, User] = {}
    if attendee_ids:
        users = await User.filter(id__in=list(attendee_ids), organization_id=organization_id)
        users_by_id = {u.id: u for u in users}
    has_agenda_by_id = await MeetingSummaryPresenter.fetch_agenda_map(meetings)
    return [
        await _meeting_response(
            meeting,
            current_user_id=current_user_id,
            for_list_view=True,
            users_by_id=users_by_id,
            has_agenda=has_agenda_by_id[meeting.id],
        )
        for meeting in meetings
    ]


Sort = Literal["scheduled_at_asc", "scheduled_at_desc"]


# Declared before `/meetings/{meeting_id}` so the literal path matches first.
@router.get("/meetings", response_model=MeetingListResponse)
async def api_meetings_index(
    current_user: User = Depends(get_current_user),
    scheduled_after: AwareDatetime | None = Query(None),
    scheduled_before: AwareDatetime | None = Query(None),
    completed: bool | None = Query(None),
    # `past` (end-time based) is a distinct concept from `completed`
    # (transcript / elapsed based); the two diverge for meetings with no
    # `scheduled_end_at`, so the past list must request `past`.
    past: bool | None = Query(None),
    collection_id: UUID | None = Query(None),
    # Filters to meetings with no collection. Mutually exclusive with
    # `collection_id`; mirrors the legacy `?filter=uncategorized` view.
    uncategorized: bool = Query(False),
    # Declined meetings are hidden by default because the upcoming list and the
    # nav "next meetings" pill both want them gone. The past list opts in to show
    # them, since a past meeting you declined may still have been recorded.
    include_declined: bool = Query(False),
    # "organization" (default) includes org-shared meetings the user can see —
    # the legacy `meetings_index` (past list) scope. "member" restricts to
    # meetings the user created or collaborates on, matching the legacy
    # `meetings_upcoming` page which used `Meeting.by_user` and did not surface
    # org-shared meetings the user isn't part of.
    scope: Literal["organization", "member"] = Query("organization"),
    sort: Sort = Query("scheduled_at_desc"),
    cursor: str | None = Query(None),
):
    if collection_id is not None:
        collection = await MeetingCollection.get_or_none(
            id=collection_id, organization_id=current_user.organization_id
        )
        if collection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    if scope == "member":
        queryset = Meeting.by_user(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
        )
    else:
        queryset = Meeting.by_organization_or_user(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
        )
    if scheduled_after is not None:
        queryset = queryset.filter(scheduled_at__gte=scheduled_after)
    if scheduled_before is not None:
        queryset = queryset.filter(scheduled_at__lt=scheduled_before)
    if completed is True:
        queryset = queryset.filter(Meeting.filters.by_completed())
    elif completed is False:
        queryset = queryset.filter(Meeting.filters.by_not_completed())
    if past is True:
        queryset = queryset.filter(Meeting.filters.by_past())
    if collection_id is not None:
        queryset = queryset.filter(Meeting.filters.by_collection(collection_id))
    elif uncategorized:
        queryset = queryset.filter(Meeting.filters.by_uncategorized())
    # Filter declined meetings in the query, before pagination, so the page
    # stays full and `has_more`/`next_cursor` reflect what the client receives.
    if not include_declined:
        queryset = queryset.filter(Meeting.filters.by_not_declined_by(current_user.id))

    direction = "" if sort == "scheduled_at_asc" else "-"
    queryset = queryset.prefetch_related(
        "organization", "workspace__collaborators__user", "jobs__job", "recording", "collection"
    ).order_by(f"{direction}scheduled_at", "id")

    pagination = await Pagination.create(Meeting, cursor=cursor, queryset=queryset)
    return MeetingListResponse(
        meetings=await _meeting_list_responses(
            pagination.results,
            current_user_id=current_user.id,
            organization_id=current_user.organization_id,
        ),
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


class CreateMeetingFromUrlRequest(BaseModel):
    type: Literal["url"] = "url"
    conferencing_url: str = Field(min_length=1)
    title: str | None = None
    scheduled_at: datetime | None = None
    sharing: Sharing | None = None

    @field_validator("conferencing_url")
    @classmethod
    def _validate_conferencing_url(cls, v: str) -> str:
        if not Meeting.is_valid_conferencing_url(v):
            raise ValueError("Please provide a valid conferencing URL from Zoom, Google Meet, or Microsoft Teams.")
        return v

    def apply_to(self, meeting: Meeting, *, now: datetime, helpers: Helpers) -> None:
        meeting.conferencing_url = self.conferencing_url
        meeting.manually_created_at = now
        meeting.title = self.title or f"Meeting at {self.conferencing_url}"
        meeting.scheduled_at = self.scheduled_at or now
        if self.sharing is not None:
            meeting.sharing = self.sharing


class CreateMeetingFromTranscriptRequest(BaseModel):
    type: Literal["transcript"] = "transcript"
    transcript: str = Field(min_length=1)
    title: str | None = None
    sharing: Sharing | None = None

    def apply_to(self, meeting: Meeting, *, now: datetime, helpers: Helpers) -> None:
        meeting.transcript = self.transcript
        meeting.manually_created_at = now
        meeting.title = self.title or f"Meeting at {datetime.now(helpers.timezone).strftime('%Y-%m-%d %H:%M:%S')}"
        meeting.scheduled_at = now
        if self.sharing is not None:
            meeting.sharing = self.sharing

    async def enqueue_post_save_jobs(self, meeting: Meeting) -> None:
        process = ProcessTranscriptJob(meeting_id=meeting.id, should_update_title=True, unique=True)
        callback = MeetingProcessingCompleteCallbackJob(meeting_id=meeting.id, unique=True)
        jobs_group = await enqueue_job_group([process], callback=callback)
        await MeetingJob.create(meeting=meeting, job=jobs_group.jobs[0])


CreateMeetingRequest = Annotated[
    CreateMeetingFromUrlRequest | CreateMeetingFromTranscriptRequest,
    Field(discriminator="type"),
]


@router.post("/meetings", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def api_meetings_create(
    body: CreateMeetingRequest,
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    now = datetime.now(UTC)
    meeting = Meeting(creator=current_user, organization_id=current_user.organization_id)
    body.apply_to(meeting, now=now, helpers=helpers)
    await meeting.save()
    if isinstance(body, CreateMeetingFromTranscriptRequest):
        await body.enqueue_post_save_jobs(meeting)
    return await _fetch_meeting_response(meeting.id, current_user.id)


@router.get("/meetings/{meeting_id}", response_model=MeetingResponse)
async def api_meetings_show(
    meeting: Meeting = Depends(get_meeting),
    current_user: User = Depends(get_current_user),
):
    return await _meeting_response(meeting, current_user_id=current_user.id)


# Lives on its own endpoint so the React island can refresh the signed URL
# on visibilitychange without re-fetching the full show payload, and so the
# show response doesn't pay the GCS signing IO when consumers don't render
# the video.
@router.get("/meetings/{meeting_id}/recording", response_model=MeetingRecordingResponse)
async def api_meetings_recording(meeting: Meeting = Depends(get_meeting)):
    if not meeting.recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    return MeetingRecordingResponse(id=str(meeting.recording_id), url=await meeting.recording.url())


# Recordings upload browser-direct to storage (GCS in prod) so multi-hundred-MB
# videos never transit the app worker. This mints a short-lived signed POST
# target; the client uploads the file to it, then PATCHes the meeting with the
# returned object key (see the recording_key branch in api_meetings_update). The
# fetch upload to GCS requires the bucket CORS to allow POST from our origin.
@router.post("/meetings/{meeting_id}/recording/upload_url", response_model=RecordingUploadTargetResponse)
async def api_meetings_recording_upload_url(meeting: Meeting = Depends(get_meeting)):
    target = await FileReference.upload_target(content_type="video/mp4", max_bytes=MAX_RECORDING_BYTES)
    return RecordingUploadTargetResponse(action=target.action, fields=target.fields, key=target.key)


# Pseudo-resource for the same reason as /recording: keeps transcript text
# (often kilobytes per meeting) out of the show + list payloads, and lets the
# transcript tab lazy-load on demand.
@router.get("/meetings/{meeting_id}/transcript", response_model=ProcessedTranscriptResponse)
async def api_meetings_transcript(meeting: Meeting = Depends(get_meeting)):
    transcript = _processed_transcript_response(meeting)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")
    return transcript


# In-meeting chat sits on its own endpoint — same reasoning as /transcript:
# kilobyte-scale Recall.ai-captured chat history is dead weight on every show
# fetch, but the Chat tab in the React island lazy-loads it once activated.
# Returns 200 with an empty list when the meeting has no chat — "no messages"
# is a normal state for text-only or audio-only meetings, not an error.
@router.get("/meetings/{meeting_id}/chat", response_model=MeetingChatListResponse)
async def api_meetings_chat(meeting: Meeting = Depends(get_meeting)):
    messages = sorted(meeting.chat_messages, key=lambda m: m.created_at)
    return MeetingChatListResponse(
        messages=[
            MeetingChatMessageResponse(
                sender_name=m.sender.name,
                text=m.text,
                created_at=_chat_created_at(m.created_at),
            )
            for m in messages
        ],
    )


def _chat_created_at(value: str | datetime) -> datetime:
    # chat_messages is a JSON column, so created_at round-trips as a datetime
    # when freshly built in-process but as an ISO string when reloaded from the
    # DB. Normalise to datetime so the response model sorts/serialises uniformly.
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


@router.patch("/meetings/{meeting_id}", response_model=MeetingResponse)
async def api_meetings_update(
    body: UpdateMeetingRequest,
    meeting: Meeting = Depends(get_meeting),
    current_user: User = Depends(get_current_user),
):
    if meeting.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This meeting has been deleted and cannot be edited.",
        )

    fields_set = body.model_fields_set

    if body.title is not None:
        meeting.title = body.title
    if body.summary is not None:
        meeting.summary = body.summary
    if body.agenda is not None:
        meeting.agenda = body.agenda
    if body.sharing is not None:
        # Setting sharing on the resource fires the workspace pre_save signal,
        # which mirrors it onto the workspace row for querying (see
        # collaboration/workspace.py::save_workspace).
        meeting.sharing = body.sharing
    if "scheduled_at" in fields_set:
        meeting.scheduled_at = body.scheduled_at

    # Resolve and validate the requested collection before any write, so a bad
    # collection_id can't leave field changes half-committed.
    collection_to_assign: MeetingCollection | None = None
    clear_collection = False
    if "collection_id" in fields_set:
        if body.collection_id is None:
            clear_collection = True
        else:
            collection_to_assign = await MeetingCollection.get_or_none(
                id=body.collection_id, organization_id=current_user.organization_id
            )
            if collection_to_assign is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    # Materialize the recording FileReference from the GCS object key the React
    # upload flow passes back after a direct-to-cloud upload. Pre-validate so a
    # bad key or empty upload can't leave field changes half-committed.
    recording_file: FileReference | None = None
    if body.recording_key is not None:
        recording_file = await FileReference.from_key(body.recording_key)
        if not recording_file.byte_size:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file was uploaded")
        meeting.recording_id = recording_file.id

    async with transaction() as connection:
        if recording_file is not None:
            await recording_file.save(using_db=connection)

        if meeting.changes:
            changed_fields = set(meeting.changes.keys())
            if "agenda" in changed_fields:
                notifier = Notifier(meeting, current_user)
                async with notifier.record_and_notify(
                    EventAction.MEETING_UPDATED, creator_id=current_user.id, using_db=connection
                ) as recording:
                    await meeting.save(using_db=recording.using_db)
            else:
                # A sharing-only change records UPDATED_SHARING so the sharing
                # transition stays distinct; any broader edit stays a generic
                # MEETING_UPDATED.
                event_action = (
                    EventAction.UPDATED_SHARING if changed_fields == {"sharing"} else EventAction.MEETING_UPDATED
                )
                async with meeting.workspace.record(
                    event_action, creator_id=current_user.id, using_db=connection
                ) as recording:
                    await meeting.save(using_db=recording.using_db)

        if clear_collection:
            await meeting.unassign_collection(current_user.id, using_db=connection)
        elif collection_to_assign is not None:
            await meeting.assign_collection(collection_to_assign, current_user.id, using_db=connection)

    return await _fetch_meeting_response(meeting.id, current_user.id)


@router.delete("/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_meetings_delete(
    meeting: Meeting = Depends(get_meeting),
    current_user: User = Depends(get_current_user),
):
    if meeting.is_upcoming:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Future meetings cannot be deleted in Convictional. Please manage this in your calendar.",
        )

    async with meeting.workspace.record(EventAction.MEETING_DELETED, creator_id=current_user.id) as recording:
        await meeting.soft_delete(using_db=recording.using_db)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Handle this surface's live-document (Yjs) broadcasts.
register_live_document_handler("meeting_agenda")
