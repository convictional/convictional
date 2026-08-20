from uuid import UUID

from app.jobs.meetings import (
    ExtractMeetingMetadataJob,
    ProcessTranscriptJob,
)
from app.models.accounts import User
from app.models.collaboration.live import LiveDocumentUpdate
from app.models.workspaces.meetings import Meeting, MeetingAttendee
from app.presenters.base import BasePresenter
from app.presenters.collaborator import CollaboratorsPresenter
from config.enums import MeetingAttendeeStatus
from infra.jobs import JobDefinitionClass
from infra.messaging import Topic


class AttendeePresenter(BasePresenter[MeetingAttendee]):
    name: str
    user: User | None
    status: MeetingAttendeeStatus = MeetingAttendeeStatus.NOT_AVAILABLE

    @classmethod
    async def create(cls, attendee: MeetingAttendee, org_users: list[User]):
        user = next((u for u in org_users if u.id == attendee.user_id), None)
        return cls(
            model=attendee,
            name=user.display_name if user else attendee.display_name,
            user=user,
            status=attendee.status,
        )


class MeetingSummaryPresenter(BasePresenter[Meeting]):
    @classmethod
    async def fetch_agenda_map(cls, meetings: list[Meeting]) -> dict[UUID, bool]:
        meetings_needing_check = [m for m in meetings if not (m.agenda and m.agenda.strip())]

        topic_name_map = {m.id: Topic("meeting_agenda", meeting_id=m.id).name for m in meetings_needing_check}
        if topic_name_map:
            topics_with_updates = set(
                await LiveDocumentUpdate.filter(topic_name__in=list(topic_name_map.values())).values_list(
                    "topic_name", flat=True
                )
            )
        else:
            topics_with_updates = set()

        result: dict[UUID, bool] = {}
        for m in meetings:
            if m.agenda and m.agenda.strip():
                result[m.id] = True
            else:
                result[m.id] = topic_name_map.get(m.id, "") in topics_with_updates
        return result


class MeetingPresenter(BasePresenter[Meeting]):
    current_user: User
    attendees: list[AttendeePresenter] = []
    user_attendees: list[User] = []
    org_users: list[User] = []
    collaborators: CollaboratorsPresenter | None = None
    chat_messages: list[dict] = []
    previous_meeting: Meeting | None = None
    next_meeting: Meeting | None = None
    agenda_markdown: str = ""

    @classmethod
    async def create(
        cls,
        meeting: Meeting,
        current_user: User,
        org_users: list[User],
    ):
        attendee_user_ids = [a.user_id for a in meeting.attendees if a.user_id]
        resolved_users = [u for u in org_users if u.id in attendee_user_ids]

        previous_meeting = None
        next_meeting = None
        if meeting.is_recurring:
            previous_meeting = await meeting.get_previous_meeting()
            next_meeting = await meeting.get_next_meeting()

        collaborators = await CollaboratorsPresenter.create(meeting.workspace)

        chat_messages = sorted(meeting.chat_messages, key=lambda x: x.created_at)

        # Fetch agenda markdown from live document for immediate display
        agenda_markdown = await meeting.get_agenda_markdown()

        return cls(
            model=meeting,
            current_user=current_user,
            attendees=[await AttendeePresenter.create(a, org_users) for a in meeting.attendees],
            user_attendees=resolved_users,
            org_users=org_users,
            collaborators=collaborators,
            chat_messages=chat_messages,
            previous_meeting=previous_meeting,
            next_meeting=next_meeting,
            agenda_markdown=agenda_markdown,
        )

    @property
    def unresolved_attendees(self):
        return [a for a in self.model.attendees if a.user_id is None]

    @property
    def initial_processing_is_busy(self):
        return self.job_is_busy(ExtractMeetingMetadataJob) or self.job_is_busy(ProcessTranscriptJob)

    @property
    def any_job_is_busy(self):
        return len(self.model.busy_jobs) > 0

    def job_is_busy(self, job_definition: JobDefinitionClass) -> bool:
        return any(isinstance(job.job_definition, job_definition) for job in self.model.busy_jobs)
