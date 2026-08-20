import base64
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field
from tortoise import fields
from tortoise.models import Model

from app.models.accounts import User
from app.models.workspaces.meetings import Meeting, MeetingAttendee, MeetingChatMessage
from config import settings
from config.enums import MeetingAttendeeStatus
from infra.db import RecordModel

BOT_NAME = "Recorder"  # Note that changes to the bot name must be applied by running RenameRecallBotJob in production

# Automatic recording preferences
# https://docs.recall.ai/docs/calendar-v1-recording-preferences#common-use-cases-and-recording-preference-combinations
RECALL_AI_PREFERENCE_MAPPING: dict[str, dict[str, bool | str]] = {
    "none": {
        "record_non_host": False,
        "record_recurring": False,
        "record_external": False,
        "record_internal": False,
        "record_confirmed": False,
        "record_only_host": False,
    },
    "all": {
        "record_non_host": False,
        "record_recurring": False,
        "record_external": True,
        "record_internal": True,
        "record_confirmed": False,
        "record_only_host": False,
    },
}


#
# Response Models (Pydantic)
#
#


class RecallAIBotStatusCodes(StrEnum):
    """
    Recall.AI bot status codes.
    https://docs.recall.ai/docs/bot-status-change-events
    """

    NONE = ""  # Internal status, not from Recall.AI - default value
    SCHEDULED = "scheduled"  # Internal status, not from Recall.AI
    UNSCHEDULABLE = "unschedulable"  # Internal status, not from Recall.AI
    DELETED = "deleted"  # Internal status, not from Recall.AI
    READY = "ready"
    JOINING_CALL = "joining_call"
    IN_WAITING_ROOM = "in_waiting_room"
    PARTICIPANT_IN_WAITING_ROOM = "participant_in_waiting_room"
    IN_CALL_NOT_RECORDING = "in_call_not_recording"
    RECORDING_PERMISSION_ALLOWED = "recording_permission_allowed"
    RECORDING_PERMISSION_DENIED = "recording_permission_denied"
    IN_CALL_RECORDING = "in_call_recording"
    CALL_ENDED = "call_ended"
    RECORDING_DONE = "recording_done"
    DONE = "done"
    FATAL = "fatal"
    ANALYSIS_DONE = "analysis_done"
    ANALYSIS_FAILED = "analysis_failed"
    MEDIA_EXPIRED = "media_expired"

    @property
    def is_completed(self) -> bool:
        return self in [RecallAIBotStatusCodes.DONE, RecallAIBotStatusCodes.FATAL]


class RecallAIBotStatusSubCodes(StrEnum):
    """
    Recall.AI bot status sub codes.
    https://docs.recall.ai/docs/sub-codes
    """

    NONE = ""

    # Recording Permission Denied Sub Codes (Zoom only)
    ZOOM_LOCAL_RECORDING_DISABLED = "zoom_local_recording_disabled"
    ZOOM_LOCAL_RECORDING_REQUEST_DISABLED = "zoom_local_recording_request_disabled"
    ZOOM_LOCAL_RECORDING_REQUEST_DISABLED_BY_HOST = "zoom_local_recording_request_disabled_by_host"
    ZOOM_BOT_IN_WAITING_ROOM = "zoom_bot_in_waiting_room"
    ZOOM_HOST_NOT_PRESENT = "zoom_host_not_present"
    ZOOM_LOCAL_RECORDING_REQUEST_DENIED_BY_HOST = "zoom_local_recording_request_denied_by_host"
    ZOOM_LOCAL_RECORDING_DENIED = "zoom_local_recording_denied"
    ZOOM_LOCAL_RECORDING_GRANT_NOT_SUPPORTED = "zoom_local_recording_grant_not_supported"
    ZOOM_SDK_KEY_BLOCKED_BY_HOST_ADMIN = "zoom_sdk_key_blocked_by_host_admin"
    # Call Ended Sub Codes
    CALL_ENDED_BY_HOST = "call_ended_by_host"
    CALL_ENDED_BY_PLATFORM_IDLE = "call_ended_by_platform_idle"
    CALL_ENDED_BY_PLATFORM_MAX_LENGTH = "call_ended_by_platform_max_length"
    CALL_ENDED_BY_PLATFORM_WAITING_ROOM_TIMEOUT = "call_ended_by_platform_waiting_room_timeout"
    TIMEOUT_EXCEEDED_WAITING_ROOM = "timeout_exceeded_waiting_room"
    TIMEOUT_EXCEEDED_NOONE_JOINED = "timeout_exceeded_noone_joined"
    TIMEOUT_EXCEEDED_EVERYONE_LEFT = "timeout_exceeded_everyone_left"
    TIMEOUT_EXCEEDED_SILENCE_DETECTED = "timeout_exceeded_silence_detected"
    TIMEOUT_EXCEEDED_ONLY_BOTS_IN_CALL = "timeout_exceeded_only_bots_in_call"
    TIMEOUT_EXCEEDED_MAX_DURATION = "timeout_exceeded_max_duration"
    BOT_KICKED_FROM_CALL = "bot_kicked_from_call"
    BOT_KICKED_FROM_WAITING_ROOM = "bot_kicked_from_waiting_room"
    BOT_RECEIVED_LEAVE_CALL = "bot_received_leave_call"
    TIMEOUT_EXCEEDED_ONLY_BOTS_DETECTED_USING_PARTICIPANT_EVENTS = (
        "timeout_exceeded_only_bots_detected_using_participant_events"
    )
    TIMEOUT_EXCEEDED_RECORDING_PERMISSION_DENIED = "timeout_exceeded_recording_permission_denied"
    # Fatal Sub Codes
    BOT_ERRORED = "bot_errored"
    MEETING_NOT_FOUND = "meeting_not_found"
    MEETING_NOT_STARTED = "meeting_not_started"
    MEETING_REQUIRES_SIGN_IN = "meeting_requires_sign_in"
    MEETING_LINK_EXPIRED = "meeting_link_expired"
    MEETING_LINK_INVALID = "meeting_link_invalid"
    MEETING_PASSWORD_INCORRECT = "meeting_password_incorrect"
    MEETING_LOCKED = "meeting_locked"
    MEETING_FULL = "meeting_full"
    MEETING_ENDED = "meeting_ended"
    GOOGLE_MEET_INTERNAL_ERROR = "google_meet_internal_error"
    GOOGLE_MEET_SIGN_IN_FAILED = "google_meet_sign_in_failed"
    GOOGLE_MEET_SIGN_IN_CAPTCHA_FAILED = "google_meet_sign_in_captcha_failed"
    GOOGLE_MEET_SIGN_IN_MISSING_LOGIN_CREDENTIALS = "google_meet_sign_in_missing_login_credentials"
    GOOGLE_MEET_SIGN_IN_MISSING_RECOVERY_CREDENTIALS = "google_meet_sign_in_missing_recovery_credentials"
    GOOGLE_MEET_SSO_SIGN_IN_FAILED = "google_meet_sso_sign_in_failed"
    GOOGLE_MEET_SSO_SIGN_IN_MISSING_LOGIN_CREDENTIALS = "google_meet_sso_sign_in_missing_login_credentials"
    GOOGLE_MEET_SSO_SIGN_IN_MISSING_TOTP_SECRET = "google_meet_sso_sign_in_missing_totp_secret"
    GOOGLE_MEET_VIDEO_ERROR = "google_meet_video_error"
    GOOGLE_MEET_MEETING_ROOM_NOT_READY = "google_meet_meeting_room_not_ready"
    GOOGLE_MEET_LOGIN_NOT_AVAILABLE = "google_meet_login_not_available"
    ZOOM_SDK_CREDENTIALS_MISSING = "zoom_sdk_credentials_missing"
    ZOOM_SDK_UPDATE_REQUIRED = "zoom_sdk_update_required"
    ZOOM_SDK_APP_NOT_PUBLISHED = "zoom_sdk_app_not_published"
    ZOOM_EMAIL_BLOCKED_BY_ADMIN = "zoom_email_blocked_by_admin"
    ZOOM_REGISTRATION_REQUIRED = "zoom_registration_required"
    ZOOM_CAPTCHA_REQUIRED = "zoom_captcha_required"
    ZOOM_ACCOUNT_BLOCKED = "zoom_account_blocked"
    ZOOM_INVALID_SIGNATURE = "zoom_invalid_signature"
    ZOOM_INTERNAL_ERROR = "zoom_internal_error"
    ZOOM_JOIN_TIMEOUT = "zoom_join_timeout"
    ZOOM_EMAIL_REQUIRED = "zoom_email_required"
    ZOOM_WEB_DISALLOWED = "zoom_web_disallowed"
    ZOOM_MEETING_NOT_ACCESSIBLE = "zoom_meeting_not_accessible"
    MICROSOFT_TEAMS_CALL_DROPPED = "microsoft_teams_call_dropped"
    MICROSOFT_TEAMS_SIGN_IN_CREDENTIALS_MISSING = "microsoft_teams_sign_in_credentials_missing"
    WEBEX_JOIN_MEETING_ERROR = "webex_join_meeting_error"


class RecallAIBotStatus(BaseModel):
    code: RecallAIBotStatusCodes
    created_at: str
    message: str | None = Field(default=None)
    sub_code: RecallAIBotStatusSubCodes | None = Field(default=None)
    recording_id: str | None = Field(default=None)


class RecallAIBotStatusData(BaseModel):
    bot_id: str
    status: RecallAIBotStatus


class RecallAIBotStatusPayload(BaseModel, extra="allow"):
    data: RecallAIBotStatusData
    event: str


def b64_encode_image(image_name: str):
    path = settings.root / "integrations" / "recall_ai" / "images" / image_name
    with open(path, "rb") as file:
        return {
            "kind": "jpeg",
            "b64_data": base64.b64encode(file.read()).decode("utf-8"),
        }


class RecallAIBotOptions(BaseModel):
    bot_name: str = BOT_NAME
    meeting_url: str
    join_at: str | None = None
    transcription_options: dict[str, str] = {"provider": "meeting_captions"}
    recording_mode: str = "gallery_view_v2"
    recording_mode_options: dict[str, Any] = {
        "participant_video_when_screenshare": "overlap",
    }
    automatic_video_output: dict[str, Any] = {
        "in_call_not_recording": b64_encode_image("loading.jpg"),
        "in_call_recording": b64_encode_image("recording.jpg"),
    }


#
# Calendar v1 Models
#
#


class RecallAIBotCalendarUser(BaseModel):
    id: str
    external_id: str


class RecallAIBotCalendarMeeting(BaseModel):
    id: str
    start_time: datetime
    end_time: datetime
    calendar_user: RecallAIBotCalendarUser


class RecallAIBot(BaseModel):
    id: str
    video_url: str | None = Field(default=None)
    media_retention_end: datetime | None = Field(default=None)
    status_changes: list[dict[str, Any]] = Field(default_factory=list)
    meeting_participants: list[dict[str, Any]] = Field(default_factory=list)
    meeting_url: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    join_at: datetime | None = Field(default=None)
    calendar_meetings: list[RecallAIBotCalendarMeeting] = Field(default_factory=list)
    recording: str | None = Field(default=None)
    recordings: list[dict[str, Any]] = Field(default_factory=list)
    include_bot_in_recording: dict[str, Any] | None = Field(default=None)


class RecallAIPlatform(StrEnum):
    GOOGLE_MEET = "google_meet"
    MICROSOFT_TEAMS = "microsoft_teams"
    MICROSOFT_TEAMS_LIVE = "microsoft_teams_live"  # This is the personal version of Teams
    UNKNOWN = "unknown"
    WEBEX = "webex"
    ZOOM = "zoom"


class RecallAIChatMessages(BaseModel):
    next: str | None = Field(default=None)
    previous: str | None = Field(default=None)
    results: list[MeetingChatMessage] = Field(default_factory=list)


class RecallAICalendarProvider(StrEnum):
    GOOGLE_CALENDAR = "google_calendar"
    MICROSOFT_OUTLOOK = "microsoft_outlook"


class RecallAICalendarAttendee(BaseModel):
    name: str | None = None
    email: str
    is_organizer: bool
    status: MeetingAttendeeStatus

    @property
    def declined_event(self) -> bool:
        return self.status == MeetingAttendeeStatus.DECLINED

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        return self.email

    def as_meeting_attendee(self, users: list[User]) -> MeetingAttendee:
        user = next((u for u in users if u.has_email(self.email)), None)
        return MeetingAttendee(
            user_id=user.id if user else None,
            name=user.display_name if user else self.display_name,
            status=self.status,
            is_organizer=self.is_organizer,
        )


class RecallAICalendarEvent(BaseModel):
    id: str
    override_should_record: bool | None = None
    title: str
    will_record: bool
    will_record_reason: str
    start_time: datetime
    end_time: datetime
    platform: str | None = None
    platform_id: str | None = None
    meeting_platform: RecallAIPlatform | None = None
    calendar_platform: str | None = None
    zoom_invite: dict[str, Any] | None = None
    teams_invite: dict[str, Any] | None = None
    meet_invite: dict[str, Any] | None = None
    webex_invite: dict[str, Any] | None = None
    bot_id: str | None = None
    is_external: bool
    is_hosted_by_me: bool
    is_recurring: bool
    organizer_email: str
    attendee_emails: list[str]
    attendees: list[RecallAICalendarAttendee]
    ical_uid: str
    visibility: str | None = None

    @property
    def is_hidden(self) -> bool:
        return len(self.attendees) <= 1 and not self.will_record

    @property
    def organizer(self) -> RecallAICalendarAttendee | None:
        return next((attendee for attendee in self.attendees if attendee.is_organizer), None)

    @property
    def is_happening_now(self) -> bool:
        now = datetime.now(UTC)
        return self.start_time <= now <= self.end_time

    @property
    def attendee_and_organizer_emails(self) -> list[str]:
        return [attendee.email for attendee in self.attendees]

    @property
    def provider_meeting_id(self) -> str:
        fallback = self.platform_id or self.ical_uid or "unknown"

        match self.meeting_platform:
            case RecallAIPlatform.GOOGLE_MEET:
                return fallback if not self.meet_invite else self.meet_invite.get("meeting_id", fallback)
            case RecallAIPlatform.ZOOM:
                return fallback if not self.zoom_invite else self.zoom_invite.get("meeting_id", fallback)
            case RecallAIPlatform.MICROSOFT_TEAMS | RecallAIPlatform.MICROSOFT_TEAMS_LIVE:
                return self.ical_uid
            case _:
                return fallback

    @property
    def meeting_url(self) -> str | None:
        match self.meeting_platform:
            case RecallAIPlatform.GOOGLE_MEET if self.meet_invite:
                return (
                    f"https://meet.google.com/{self.meet_invite.get('meeting_id')}"
                    if self.meet_invite.get("meeting_id", None)
                    else None
                )
            case RecallAIPlatform.ZOOM if self.zoom_invite:
                return f"https://zoom.us/j/{self.zoom_invite.get('meeting_id')}"
            case _:
                return None

    def unique_event_id(self, organization_id: UUID) -> str:
        """
        event.id is not unique between user's calendars.
        ical_uid is not always unique - depending on how the calendar event is created.
        provider_meeting_id is consistent regardless of how the calendar event is created and
        persists across (most) calendar event updates.
        organization_id is appended to ensure uniqueness between organizations
        """
        start_date = self.start_time.strftime("%Y-%m-%d")
        return f"{self.provider_meeting_id}-{start_date}-{organization_id}"

    def declined_by_email(self, user_email: str) -> bool:
        if not self.attendees:
            return False
        for attendee in self.attendees:
            if attendee.email == user_email:
                return attendee.declined_event
        return False


class RecallAICalendarPreferences(StrEnum):
    NONE = "none"
    ALL = "all"
    INTERNAL_ONLY = "internal_only"
    EXTERNAL_ONLY = "external_only"


#
# Record models
#
#


class RecallAICalendarUser(Model):
    id = fields.CharField(primary_key=True, max_length=255)
    external_id: str = fields.TextField()
    connections: list[dict[str, str | bool | None]] = fields.JSONField(default=list)
    preferences: dict[str, bool | str] = fields.JSONField(default=dict)

    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User", db_index=True)
    user_id: Annotated[UUID, "foreign key to user"]

    class Meta:
        indexes = (("id"), ("user_id"))
        unique_together = ("id", "user_id")

    @property
    def is_connected(self) -> bool:
        if not self.connections:
            return False

        return any([connection for connection in self.connections if connection["connected"]])

    @property
    def preference_name(self):
        if not self.preferences:
            return None
        # Remove unrelated fields from the preferences object
        self.preferences.pop("id", None)
        self.preferences.pop("bot_name", None)
        # Find the preference mapping that matches the user's preferences
        for preference, mapping in RECALL_AI_PREFERENCE_MAPPING.items():
            # Check if all values in the user's preferences match the values in a mapping,
            # note the order of the keys is not fixed
            for key, value in self.preferences.items():
                if mapping.get(key) != value:
                    break
            else:
                return RecallAICalendarPreferences(preference)

        raise ValueError(f"Invalid preferences: {self.preferences}")

    async def update_from_response(self, response: dict[str, Any]):
        self.connections = response.get("connections", [])
        self.preferences = response.get("preferences", {})
        await self.save(update_fields=["connections", "preferences"])


class RecallAIMeeting(RecordModel):
    meeting: fields.ForeignKeyRelation[Meeting] = fields.ForeignKeyField(
        "convictional.Meeting", related_name="recall_ai_meeting", db_index=True
    )
    meeting_id: Annotated[UUID, "foreign key to meeting"]
    external_id = fields.CharField(max_length=500, null=True, unique=True)
    provider_meeting_id: str | None = fields.TextField(max_length=500, null=True)
    bot_id: str | None = fields.TextField(max_length=500, null=True)
    bot_status = fields.CharEnumField(RecallAIBotStatusCodes, default=RecallAIBotStatusCodes.NONE, max_length=255)
    bot_sub_status = fields.CharEnumField(
        RecallAIBotStatusSubCodes, default=RecallAIBotStatusSubCodes.NONE, max_length=255
    )
    meeting_platform: RecallAIPlatform | None = fields.CharEnumField(RecallAIPlatform, null=True, max_length=255)
    will_record = fields.BooleanField(default=False)

    class Meta:
        indexes = (("id"), ("meeting_id"), ("bot_id"), ("external_id"))

    @property
    def is_schedulable(self) -> bool:
        if not self.meeting.scheduled_at:
            return False
        return self.meeting.scheduled_at > datetime.now(UTC) + timedelta(minutes=20)

    @property
    def is_scheduled(self) -> bool:
        if not self.bot_id:
            return False
        return self.bot_status == RecallAIBotStatusCodes.SCHEDULED

    @property
    def is_supported_meeting_platform(self) -> bool:
        if not self.meeting_platform:
            return False

        if self.meeting_platform not in settings.recall_ai_meeting_platforms.values():
            return False

        if self.meeting_platform == RecallAIPlatform.WEBEX:
            return False

        return True

    def mark_recall_ai_bot_scheduled(self):
        self.bot_status = RecallAIBotStatusCodes.SCHEDULED

    def mark_recall_ai_bot_unschedulable(self):
        self.bot_status = RecallAIBotStatusCodes.UNSCHEDULABLE
