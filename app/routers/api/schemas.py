from datetime import datetime, time
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Discriminator,
    EmailStr,
    Field,
    Tag,
    field_serializer,
    field_validator,
    model_validator,
)

from config.enums import (
    EventAction,
    FlashLevel,
    PushProtocol,
    SubscriptionLevel,
    UpdateFrequency,
)
from lib.strings import normalize_name

if TYPE_CHECKING:
    from app.models.collaboration.mailbox import MailboxEntry

#
# Shared list-envelope base
#
# Every list response inherits from this so clients can treat list responses
# uniformly. Resource-named field (e.g. `chats`, `goals`, `comments`) is added
# by the subclass alongside any per-resource metadata.
#


class PaginatedResponse(BaseModel):
    # Defaults match the unpaginated case so endpoints without pagination
    # don't have to restate them. Paginated endpoints always pass real
    # values sourced from `infra.db.Pagination`.
    next_cursor: str | None = None
    has_more: bool = False


# Common mailbox-entry shape shared between the list endpoint
# (MailboxEntryResponse in mailbox_entries.py) and the resource-show
# endpoints (e.g. EmailThreadMailboxEntryResponse below). Show endpoints add
# resource-specific flags; `from_entry` maps a MailboxEntry to the concrete
# subclass, so it's the single home for that mapping (email threads carry extra
# required fields and build their own).
class MailboxEntryBase(BaseModel):
    id: str
    is_unread: bool
    is_archived: bool
    is_snoozed: bool
    snoozed_until: datetime | None

    @classmethod
    def from_entry(cls, entry: "MailboxEntry") -> Self:
        return cls(
            id=str(entry.id),
            is_unread=entry.is_unread,
            is_archived=entry.is_archived,
            is_snoozed=entry.is_snoozed_now,
            snoozed_until=entry.snoozed_until,
        )


#
# Shared response models
#


class UserResponse(BaseModel):
    id: str
    display_name: str
    picture: str | None


class ProfileResponse(BaseModel):
    name: str | None
    bio: str | None
    time_zone: str | None
    picture: str | None
    has_custom_avatar: bool  # avatar_file_id is set → the UI offers a "Reset" affordance
    # The curated dropdown list of timezones is display-only (the backend accepts any
    # valid IANA zone, not just the curated ones) and its labels are UI copy, so it
    # lives in the frontend, not on this resource.


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    bio: str | None = None
    time_zone: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name_field(cls, value: str | None) -> str | None:
        return normalize_name(value) if value is not None else value

    @field_validator("time_zone")
    @classmethod
    def validate_time_zone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            # ValueError also covers malformed paths like "../../etc/passwd".
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Invalid timezone") from exc
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class ClientConfigResponse(BaseModel):
    klipy_api_key: str | None


class FlashResponse(BaseModel):
    # Server flashes set before an SPA full-document load (e.g. by a redirect).
    # The SPA shell has no Jinja flash container, so they ride along in the
    # bootstrap payload and are drained into the React toaster on mount. The
    # client collapses the four levels onto the toaster's two.
    content: str
    level: FlashLevel


class CurrentUserResponse(BaseModel):
    id: str
    display_name: str
    email: str
    is_superuser: bool
    picture: str | None
    client_config: ClientConfigResponse
    # Bootstrap fields for the React AppShell, which renders the authenticated
    # chrome with no Jinja involvement and so cannot read these from data-props.
    is_admin: bool
    organization_id: str
    organization_name: str | None
    time_zone: str | None
    feedback_upload_url: str
    flashes: list[FlashResponse]


class GroupResponse(BaseModel):
    id: str
    name: str


class OrganizationMembersResponse(BaseModel):
    users: list[UserResponse]
    groups: list[GroupResponse]


class OrganizationResponse(BaseModel):
    id: str
    name: str | None
    # Superuser-only "Support Fields" value. The field is *omitted entirely* for non-superusers
    # (the endpoint uses response_model_exclude_unset and only sets it for superusers) rather than
    # returned as null — so null unambiguously means "superuser, no prompt set", and absence means
    # "not your scope". A non-superuser never sees the key.
    system_prompt: str | None = None


class OrganizationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    # Superuser-only; the handler enforces that and is free to clear it (present → set,
    # including to "" — which is why this is keyed off model_fields_set, not None).
    system_prompt: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        # name=None is a no-op (the handler never clears name), so require an actionable field:
        # a non-null name, or system_prompt present (which may legitimately be null, to clear it).
        if self.name is None and "system_prompt" not in self.model_fields_set:
            raise ValueError("must set name and/or system_prompt")
        return self


# The admin "Team Members" surface. `users` (account administration) is deliberately distinct
# from the lightweight `members` roster above: this list is admin-only and carries the richer
# per-user fields the management UI needs (email, admin flag, lifecycle state, groups). A member's
# top goal is intentionally NOT embedded — it's its own resource (GET /api/users/{id}/top_goal),
# fetched separately like /api/people does (see app/routers/api/user_goals.py).
class OrganizationUserResponse(UserResponse):
    email: str
    bio: str | None
    is_admin: bool
    # Explicit positive lifecycle state (not is_deleted). A deactivated member still exists and is
    # restorable, so this is a reversible flag the client tabs on — toggled via PATCH, never DELETE.
    active: bool
    groups: list[GroupResponse]


class OrganizationUsersListResponse(PaginatedResponse):
    users: list[OrganizationUserResponse]


class OrganizationUserInviteRequest(BaseModel):
    email: EmailStr
    # Bounded — flows straight into the invite email job payload.
    note: str = Field(default="", max_length=1000)


class OrganizationUserUpdateRequest(BaseModel):
    is_admin: bool | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if self.is_admin is None and self.active is None:
            raise ValueError("must set is_admin and/or active")
        return self


class UpdatesConfigurationResponse(BaseModel):
    # Structured schedule fields, null until a schedule is configured (no raw cron string is
    # exposed — that's an internal storage detail). day_of_week is also null for monthly
    # schedules, where it doesn't apply.
    frequency: UpdateFrequency | None
    hour: int | None
    day_of_week: str | None
    goal_update_question: str
    has_goals: bool
    # Updates are only actually sent when a schedule, a question, and open goals all exist.
    enabled: bool


class UpdatesConfigurationUpdateRequest(BaseModel):
    frequency: UpdateFrequency | None = None
    hour: int | None = None
    day_of_week: str | None = None
    goal_update_question: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        # Require an actionable change, not just any present key: a complete schedule update
        # ("frequency" implies "hour" via schedule_fields_paired below) or a non-null
        # goal_update_question. This rejects no-op bodies the handler would silently drop —
        # {}, {"day_of_week": ...} alone, {"goal_update_question": null} — while keeping
        # {"goal_update_question": ""} valid (empty string disables goal updates).
        sets_schedule = "frequency" in self.model_fields_set
        sets_question = "goal_update_question" in self.model_fields_set and self.goal_update_question is not None
        if not (sets_schedule or sets_question):
            raise ValueError("must set a schedule (frequency + hour) or goal_update_question")
        return self

    @model_validator(mode="after")
    def schedule_fields_paired(self) -> Self:
        # The cron schedule is rebuilt from frequency + hour together, so a request that sets
        # only one of them can't be applied — reject it rather than silently dropping the field.
        if ("frequency" in self.model_fields_set) != ("hour" in self.model_fields_set):
            raise ValueError("frequency and hour must be provided together")
        return self


class ReactionUserResponse(BaseModel):
    id: str
    display_name: str


#
# Shared comment models
#
# Used by document_comments and post_draft_comments which share
# the mark-based threading model. Goal comments use a different
# threading model (parent_id + replies) and define their own.
#


class CommentMarkResponse(BaseModel):
    id: str
    global_id: str = Field(description="GlobalID used to reference this comment across resources.")
    content: str
    quoted_text: str
    comment_mark_id: str
    resolved_at: datetime | None
    created_at: datetime
    user: UserResponse
    reactions: dict[str, list[ReactionUserResponse]]


class CommentMarkListResponse(PaginatedResponse):
    comments: list[CommentMarkResponse]


# A single comment thread (all comments sharing one comment_mark_id), used as
# the response shape from the /resolve toggle. The thread is the unit of work,
# not the list of comments inside it.
class CommentThreadResponse(BaseModel):
    comment_mark_id: str
    resolved_at: datetime | None
    comments: list[CommentMarkResponse]


class CommentEditRequest(BaseModel):
    content: str | None = None
    resolved: bool | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("content must not be blank")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if self.content is None and self.resolved is None:
            raise ValueError("must set content and/or resolved")
        return self


class CommentMarkCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    quoted_text: str = ""
    comment_mark_id: str = Field(default="", max_length=36)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


#
# Content response models
#


class ContentResponse(BaseModel):
    model_config = ConfigDict(title="Content")

    id: str = Field(description="Unique ID")
    title: str = Field(description="Content title")
    author: str | None = Field(description="Author name")
    content_type: str = Field(description="Type of content (e.g. meeting, post, document)")
    category: str = Field(description="Content category (document, activity, person)")
    source_url: str = Field(description="Link to the original resource")
    preview_content: str | None = Field(description="Short preview of the content")
    created_at: datetime = Field(description="When the content was created")
    updated_at: datetime = Field(description="When the content was last updated")
    relevance_score: float | None = Field(default=None, description="Pure relevance score without recency boost")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Content-type-specific metadata")
    shared_with_me: bool = Field(default=False, description="Whether this content was shared by another user")


class DetailedContentResponse(ContentResponse):
    model_config = ConfigDict(title="DetailedContent")

    index_content: str = Field(description="Full text body of the content")


#
# Timeline response models
#


class TimelineCommentResponse(BaseModel):
    id: str
    content: str
    user: UserResponse | None


class TimelineGoalUpdateResponse(BaseModel):
    id: str
    question_text: str
    answer_text: str | None
    status: str
    progress: float | None
    requested_by: UserResponse | None


class TimelineEventResponse(BaseModel):
    id: str
    action: str
    created_at: datetime
    creator: UserResponse | None
    details: dict[str, Any]
    owner: UserResponse | None
    group: GroupResponse | None
    replies: list["TimelineEventResponse"]
    comment: TimelineCommentResponse | None = None
    goal_update: TimelineGoalUpdateResponse | None = None


# Content only. Seen-by ("readers") and the viewer's last-seen cursor are derived on the
# client from the shared collaborators view_state query, not embedded here.
class TimelineResponse(BaseModel):
    events: list[TimelineEventResponse]


#
# Subscription models
#


class SubscriptionResponse(BaseModel):
    wants_all: bool
    is_explicit: bool


class SubscriptionUpdateRequest(BaseModel):
    level: SubscriptionLevel


#
# Decision models
#
# Decisions are workspace-scoped and anchor to a comment polymorphically via
# comment_gid, so one schema serves all five surfaces (post, goal, document,
# chat, email thread).
#


class DecisionResponse(BaseModel):
    id: str
    comment_gid: str = Field(description="GlobalID of the anchored comment.")
    comment_preview: str | None = Field(
        description="Raw content of the anchored comment; clients striptag and truncate"
        " for the summary row. null means the anchor comment is deleted — render a"
        " tombstone, the decision itself stands."
    )
    decided_by: UserResponse | None
    decided_at: datetime


class DecisionListResponse(PaginatedResponse):
    decisions: list[DecisionResponse]


class DecisionCreateRequest(BaseModel):
    comment_gid: str = Field(
        description="GlobalID of the comment to mark as the decision,"
        " as returned in the global_id field of comment responses.",
        examples=["gid://convictional/PostComment/123e4567-e89b-12d3-a456-426614174000"],
    )


#
# Notification settings models
#
#


class NotificationPreferenceResponse(BaseModel):
    resource_type: str
    default_level: SubscriptionLevel


class PostGroupMuteResponse(BaseModel):
    group_id: str
    group_name: str
    muted: bool


#
# Push notification models
#


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=512)
    auth: str = Field(min_length=1, max_length=512)


class WebPushSubscriptionCreateRequest(BaseModel):
    protocol: Literal[PushProtocol.WEB_PUSH] = PushProtocol.WEB_PUSH
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: PushSubscriptionKeys
    user_agent: str | None = None
    # When the browser rotates a subscription, the service-worker
    # pushsubscriptionchange handler posts the old endpoint here so the server
    # can soft-delete the rotated row in the same request that registers the
    # replacement.
    rotated_from: str | None = None


class ApnsPushSubscriptionCreateRequest(BaseModel):
    protocol: Literal[PushProtocol.APNS]
    # 2048 matches the web-push endpoint cap; APNs/Expo device tokens are
    # much shorter in practice. Same shape will fit FCM when Android ships.
    device_token: str = Field(min_length=1, max_length=2048)
    user_agent: str | None = None


def _push_subscription_discriminator(value: Any) -> str:
    # Missing `protocol` → web_push. Lets the legacy service-worker payload
    # (which predates the discriminator field) round-trip through the unified
    # endpoint while the SW cache rotates. Drop the default once telemetry
    # shows zero no-protocol POSTs.
    if isinstance(value, dict):
        return value.get("protocol") or PushProtocol.WEB_PUSH.value
    return getattr(value, "protocol", PushProtocol.WEB_PUSH).value


# Discriminated body: one endpoint, per-protocol required fields,
# `protocol` selects the variant. New protocols (e.g. FCM) add a new Tagged
# variant here, not a new endpoint.
PushSubscriptionCreateRequest = Annotated[
    Annotated[WebPushSubscriptionCreateRequest, Tag(PushProtocol.WEB_PUSH.value)]
    | Annotated[ApnsPushSubscriptionCreateRequest, Tag(PushProtocol.APNS.value)],
    Discriminator(_push_subscription_discriminator),
]


class PushSubscriptionResponse(BaseModel):
    id: str
    protocol: PushProtocol
    # The endpoint is a tracking-vector token (it partly identifies the
    # device's push relay). We only echo the last 12 characters, prefixed
    # with an ellipsis, so support staff can spot-check "same device?" without
    # exposing the full URL to anything that renders the settings page.
    endpoint_suffix: str
    user_agent: str | None
    platform: str | None
    created_at: datetime


class PushSubscriptionListResponse(PaginatedResponse):
    subscriptions: list[PushSubscriptionResponse]


class PushWorkingHoursResponse(BaseModel):
    start: time
    end: time

    # `<input type="time">` emits "HH:MM" without seconds; matching that on the
    # wire keeps round-trip comparisons honest (server echo == client value) and
    # avoids cosmetic flicker as inputs reset from "09:00:00" back to "09:00".
    @field_serializer("start", "end")
    def serialize_time(self, value: time) -> str:
        return value.strftime("%H:%M")


class PushWorkingHoursUpdateRequest(BaseModel):
    # Pair-or-nothing on the wire: both null clears the window (push at any time);
    # both set stores explicit hours. A mixed pair has no coherent meaning here.
    start: time | None
    end: time | None

    @model_validator(mode="after")
    def pair_or_nothing(self) -> Self:
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must both be set or both be null")
        if self.start is not None and self.start == self.end:
            raise ValueError("start and end must differ (use null/null to clear working hours)")
        return self


class PushSettingsResponse(BaseModel):
    devices: list[PushSubscriptionResponse]
    # Echoed so the React island can pass it to PushManager.subscribe without
    # a second roundtrip and without a separate data-props channel.
    vapid_public_key: str
    working_hours: PushWorkingHoursResponse | None


class NotificationsResponse(BaseModel):
    preferences: list[NotificationPreferenceResponse]
    post_group_mutes: list[PostGroupMuteResponse]
    push: PushSettingsResponse


class NotificationPreferenceUpdateRequest(BaseModel):
    default_level: SubscriptionLevel


class PostGroupMuteUpdateRequest(BaseModel):
    muted: bool


#
# Workspace collaborator models
#


class CollaboratorViewStateResponse(BaseModel):
    viewed: bool
    last_viewed_at: datetime | None = None
    last_viewed_event_id: UUID | None = None


class WorkspaceCollaboratorResponse(BaseModel):
    id: str
    user: UserResponse
    is_removable: bool
    status: str  # "approved" | "pending"
    view_state: CollaboratorViewStateResponse


class WorkspaceViewerResponse(BaseModel):
    user: UserResponse
    view_state: CollaboratorViewStateResponse


class WorkspaceCollaboratorsResponse(BaseModel):
    collaborators: list[WorkspaceCollaboratorResponse]
    pending: list[WorkspaceCollaboratorResponse]
    present_user_ids: list[str]
    # Non-collaborator viewers (org members who opened an organization-shared resource) who have a
    # recorded visit. Seen-by is derived from collaborators + viewers, so a casual viewer still shows
    # up in others' "Seen by" — collaborators alone would drop them (regression vs the old timeline).
    # Excludes the requesting user, whose own state rides current_user_view_state.
    viewers: list[WorkspaceViewerResponse] = []
    # The requesting user's own view state, resolved even when they aren't a collaborator (e.g. an
    # org member viewing an organization-shared goal). The client anchors its "New activity"
    # divider on this, which the collaborators list alone can't supply for a non-collaborator.
    current_user_view_state: CollaboratorViewStateResponse


class WorkspaceCollaboratorTypeaheadUser(BaseModel):
    id: UUID
    display_name: str
    is_collaborator: bool


class WorkspaceCollaboratorTypeaheadResponse(PaginatedResponse):
    users: list[WorkspaceCollaboratorTypeaheadUser]


class WorkspaceCollaboratorAddRequest(BaseModel):
    user_id: UUID
    reason: str = ""


class WorkspaceCollaboratorInviteRequest(BaseModel):
    email: EmailStr
    reason: str = ""


class WorkspaceAccessRequest(BaseModel):
    id: UUID
    created_at: datetime


class WorkspaceAccessRequestState(BaseModel):
    workspace_id: UUID
    resource_label: str  # Human-readable resource type, e.g. "meeting", "post draft"
    request: WorkspaceAccessRequest | None


class WorkspaceAccessRequestSubmit(BaseModel):
    note: str = ""


class WorkspaceAccessRequestSubmitResponse(BaseModel):
    request: WorkspaceAccessRequest
    # Set when the requestor can read the resource (e.g. org-visible). The React client
    # navigates here on success; otherwise it shows the "Access requested" confirmation in place.
    redirect_url: str | None


#
# Email draft models
#

# RFC 5321 maximum forward path; RFC 5322 maximum line length.
EMAIL_ADDRESS_MAX = 320
EMAIL_SUBJECT_MAX = 998
EMAIL_RECIPIENTS_MAX = 100
EMAIL_BODY_MAX = 10_000_000

EmailAddressStr = Annotated[str, Field(max_length=EMAIL_ADDRESS_MAX)]


class AttachmentUploadResponse(BaseModel):
    download_url: str


class AttachmentUploadListResponse(PaginatedResponse):
    attachments: list[AttachmentUploadResponse]


class EmailDraftAttachmentResponse(BaseModel):
    id: str
    filename: str
    content_type: str | None
    is_inline: bool
    download_url: str


class DraftEnvelopeResponse(BaseModel):
    to: list[str]
    cc: list[str]
    bcc: list[str]
    subject: str
    in_reply_to_id: str | None
    attachments: list[EmailDraftAttachmentResponse]
    sendable_by: str
    can_reply: bool
    cannot_send_reason: str | None
    is_scheduled: bool
    scheduled_for: datetime | None
    # Persisted rendered body HTML, set when the draft is scheduled/sent. Null for
    # an editable draft whose live body still lives in the collaborative document.
    # Rendered by the same EmailMessageBody path as sent mail (quotes included).
    body_html: str | None = None


class DraftEnvelopeUpdateRequest(BaseModel):
    # Absent keys are preserved on the server — this is the per-field dirty-flag
    # protocol the React composer relies on so disjoint concurrent writes don't
    # clobber each other.
    to: list[EmailAddressStr] | None = Field(default=None, max_length=EMAIL_RECIPIENTS_MAX)
    cc: list[EmailAddressStr] | None = Field(default=None, max_length=EMAIL_RECIPIENTS_MAX)
    bcc: list[EmailAddressStr] | None = Field(default=None, max_length=EMAIL_RECIPIENTS_MAX)
    subject: str | None = Field(default=None, max_length=EMAIL_SUBJECT_MAX)

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("must set at least one field")
        return self


class DraftComposeRequest(BaseModel):
    # The recipient fields accept bare RFC 5321 addresses ("jane@example.com"), not
    # display-name format ("Jane <jane@example.com>"). The React composer's chip
    # input is responsible for normalization; the legacy HTML path runs an extra
    # EmailAddress.parse_list_addresses pass that the JSON contract deliberately
    # does not mirror.
    subject: str = Field(default="", max_length=EMAIL_SUBJECT_MAX)
    to: list[EmailAddressStr] = Field(default_factory=list, max_length=EMAIL_RECIPIENTS_MAX)
    cc: list[EmailAddressStr] = Field(default_factory=list, max_length=EMAIL_RECIPIENTS_MAX)
    bcc: list[EmailAddressStr] = Field(default_factory=list, max_length=EMAIL_RECIPIENTS_MAX)
    message_body: str = Field(default="", max_length=EMAIL_BODY_MAX)
    should_archive: bool = False


class DraftSendRequest(DraftComposeRequest):
    should_snooze: bool = False
    snoozed_until: datetime | None = None


class DraftScheduleRequest(DraftComposeRequest):
    # AwareDatetime rejects a naive value at parse time (422) so a mis-timed send can't reach the
    # perform_at enqueue. Normalized to UTC in the endpoint. Snooze-on-send is intentionally not
    # offered for a scheduled send — only archive.
    scheduled_for: AwareDatetime


class DraftScheduleResponse(BaseModel):
    scheduled_for: datetime
    # Rendered body so the acting tab can show the read-only preview without a refetch.
    body_html: str | None = None


class ComposerSnoozePreset(BaseModel):
    value: str
    description: str


class ComposerResponse(BaseModel):
    """Wire shape consumed by the React EmailComposer island."""

    thread_id: str
    draft_message_id: str
    current_user: UserResponse
    upload_url: str
    attachments_base_url: str
    patch_url: str
    send_url: str
    schedule_url: str
    unschedule_url: str
    delete_url: str
    draft_url: str
    initial_envelope: DraftEnvelopeResponse
    is_shared_draft: bool
    mailbox_index_url: str
    default_snooze_times: list[ComposerSnoozePreset]
    # focus_body is supplied by the React loader from its bootstrap data-props,
    # not by the server — different mount paths (initial SSR vs. bridge-fetched
    # post-DRAFT_STARTED) want different defaults.


#
# Email thread show models
#


class EmailMessageAttachmentResponse(BaseModel):
    id: str
    filename: str
    content_type: str | None
    is_inline: bool
    download_url: str
    show_in_list: bool


class EmailMessageHeaderResponse(BaseModel):
    name: str
    value: str


class EmailMessageSummaryResponse(BaseModel):
    # The metadata-only message shape used by the thread timeline and the new-message
    # broadcast. It deliberately carries no body: sanitizing email HTML is CPU-bound and,
    # across a long thread, would block the event loop. The body, attachments, and raw
    # headers are a sub-resource fetched on demand from content_url (and the detail
    # endpoint), so the server takes no view on how or when the client renders a message.
    id: str
    message_type: str
    subject: str | None
    raw_sender: str | None
    sender_name: str
    sender_email: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    preview: str | None
    received_at: datetime | None
    sent_at: datetime | None
    created_at: datetime
    external_thread_id: str | None
    message_id: str | None
    content_url: str
    reply_url: str
    forward_url: str
    view_original_url: str


class EmailMessageResponse(EmailMessageSummaryResponse):
    # The fully-materialized message, served by the detail endpoint
    # (GET .../email_messages/{id}). Adds the body, headers, raw data, and
    # attachments that the summary deliberately omits.
    # The sanitized body. Sanitizing email HTML is CPU-bound, so only the detail and
    # content endpoints produce it — never the timeline summary, which keeps a long
    # thread (many large bodies) from blocking the worker long enough to trip the
    # gunicorn timeout.
    content_html: str | None
    body_plain: str | None
    # Raw, unsanitized HTML — only the detail endpoint needs it. Keeping it off the
    # timeline summary avoids doubling per-message HTML on the wire and keeps the
    # unsanitized value out of responses that don't need it.
    body_html: str | None
    headers: list[EmailMessageHeaderResponse]
    # Requires a per-message file read, so only the detail endpoint populates it.
    raw_data: dict[str, Any] | None
    attachments: list[EmailMessageAttachmentResponse]


class ReplyPreview(BaseModel):
    # A quote of another comment by id; is_deleted signals the target was soft-deleted
    # so the quote renders a tombstone rather than its (now-hidden) content.
    id: str
    user_name: str
    content_preview: str
    is_deleted: bool


class EmailThreadCommentResponse(BaseModel):
    id: str
    global_id: str = Field(description="GlobalID used to reference this comment across resources.")
    content: str
    user: UserResponse | None
    created_at: datetime
    updated_at: datetime
    reactions: dict[str, list[ReactionUserResponse]]
    link_preview: "LinkPreviewResponse | None" = None
    attachments: list[EmailMessageAttachmentResponse] = []
    reply_to: ReplyPreview | None = None


class EmailThreadCommentListResponse(PaginatedResponse):
    comments: list[EmailThreadCommentResponse]


class EmailThreadCommentBaseRequest(BaseModel):
    content: str = Field(min_length=1)
    attachment_claim_id: UUID | None = None
    unfurl_links: bool = True

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


class EmailThreadCommentCreateRequest(EmailThreadCommentBaseRequest):
    # Reply target is a create-only field, so it lives here rather than on the shared
    # base — the edit request must not advertise a field it silently ignores.
    reply_to_id: UUID | None = None


class EmailThreadCommentEditRequest(EmailThreadCommentBaseRequest):
    # Distinct type so edit-only fields (e.g. attachment-retention flags) can
    # diverge later without touching the create contract.
    pass


# Only the actions a user can produce on an email thread get a structured detail
# payload: assignment changes and collaborator additions (`commented` renders as
# a native comment, not an event). Any other action has no detail and renders
# nothing. Discriminated on `details.type`.
class EmailThreadEventAssignmentDetails(BaseModel):
    type: Literal[EventAction.ASSIGNED, EventAction.UNASSIGNED]
    subject_label: str | None  # assignee name or email


class EmailThreadEventCollaboratorDetails(BaseModel):
    type: Literal[EventAction.ADDED_COLLABORATOR]
    subject_label: str | None  # collaborator name or email
    reason: str | None


EmailThreadEventDetails = Annotated[
    EmailThreadEventAssignmentDetails | EmailThreadEventCollaboratorDetails,
    Field(discriminator="type"),
]


class EmailThreadEventResponse(BaseModel):
    id: str
    action: str
    created_at: datetime
    creator: UserResponse | None
    # None when the action carries no renderable detail (an action without a
    # structured payload renders nothing in the timeline).
    details: EmailThreadEventDetails | None


class EmailThreadTimelineItemResponse(BaseModel):
    type: Literal["message", "event"]
    item_id: str
    created_at: datetime
    message: EmailMessageSummaryResponse | None = None
    event: EmailThreadEventResponse | None = None


class EmailThreadCreatorResponse(BaseModel):
    id: str
    display_name: str


class EmailThreadDetailResponse(BaseModel):
    id: str
    title: str
    workspace_id: str
    creator: EmailThreadCreatorResponse
    can_reply: bool
    is_shared: bool
    own_thread_id: str | None


class EmailThreadMailboxEntryResponse(MailboxEntryBase):
    is_ai_excluded: bool
    is_shared: bool
    read_at: datetime | None


class EmailThreadDraftResponse(BaseModel):
    message_id: str
    composer_url: str


class EmailThreadShowResponse(BaseModel):
    thread: EmailThreadDetailResponse
    mailbox_entry: EmailThreadMailboxEntryResponse
    timeline: list[EmailThreadTimelineItemResponse]
    comments: list[EmailThreadCommentResponse]
    draft: EmailThreadDraftResponse | None
    last_event_id: str | None


class EmailMessageContentResponse(BaseModel):
    content_html: str
    body_plain: str | None
    attachments: list[EmailMessageAttachmentResponse]


class EmailMessageContentItem(EmailMessageContentResponse):
    # Carries the message id so the batch endpoint's caller can map each body back
    # to its timeline message.
    id: str


class EmailMessageContentListResponse(PaginatedResponse):
    # Batch peer of the per-message content endpoint: the client fetches the bodies of
    # the messages it renders expanded on load in a single request, instead of one
    # request per message. The timeline stays body-free and the server stays agnostic
    # to which messages render expanded — the client just names the ids it wants.
    # Order follows the thread's message order, not the order of requested ids; callers
    # map results by id.
    contents: list[EmailMessageContentItem]


#
# Post show models
#


class LinkPreviewFileResponse(BaseModel):
    file_name: str
    content_type: str | None
    byte_size: int | None

    @classmethod
    def from_attrs(cls, attrs: dict[str, Any] | None) -> "LinkPreviewFileResponse | None":
        return cls(**attrs) if attrs else None


class LinkPreviewResponse(BaseModel):
    url: str
    title: str | None
    description: str | None
    image_url: str | None
    # Internal resource kind (goal/post/document/file/…) derived from the URL, or None for
    # external links. Lets the shared LinkPreviewCard render a native card — e.g. a file card
    # for an attachment link — instead of a generic preview, matching chat.
    resource_kind: str | None = None
    # Display metadata for a pasted attachment link (resource_kind == "file"), resolved at
    # serialize time from the reader's attachment access; null for non-file previews.
    file: LinkPreviewFileResponse | None = None


class PostCommentResponse(BaseModel):
    id: str
    global_id: str = Field(description="GlobalID used to reference this comment across resources.")
    content: str
    parent_id: str | None
    created_at: datetime
    updated_at: datetime
    user: UserResponse
    reactions: dict[str, list[ReactionUserResponse]]
    replies: list["PostCommentResponse"]
    link_preview: LinkPreviewResponse | None


class PostCommentListResponse(PaginatedResponse):
    comments: list[PostCommentResponse]


class PostViewsGroupResponse(BaseModel):
    id: str
    name: str
    seen_count: int
    total_audience: int


class PostViewsTimelineEntry(BaseModel):
    window_start: datetime
    count: int


class PostViewsResponse(BaseModel):
    seen_count: int
    total_audience: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    group: PostViewsGroupResponse | None
    # Bucketed view counts from the post's publish time to now. Clients render
    # the sparkline + compute max/percent themselves; tooltips localize off
    # first_seen_at / last_seen_at.
    views: list[PostViewsTimelineEntry]


class PostMailboxEntryResponse(MailboxEntryBase):
    pass


class GoalMailboxEntryResponse(MailboxEntryBase):
    pass


class PostPermissionsResponse(BaseModel):
    edit: bool
    pin: bool
    delete: bool


class PostResponse(BaseModel):
    # The canonical post representation, returned everywhere a published post is:
    # the list (`GET /api/posts`), show (`GET /api/posts/{id}`), and the
    # decision/pin/update PATCH endpoints. Drafts are never returned by show (it
    # 404s on a draft) and carry collaborators rather than comment data, so they
    # have their own `PostDraftResponse`.
    id: str
    title: str
    creator: UserResponse
    group: GroupResponse | None
    workspace_id: str
    is_announcement: bool
    is_pinned: bool
    pinned_at: datetime | None
    # No decision fields: decisions live in the Decision model. The show island
    # loads them from GET /api/workspaces/{id}/decisions; the index card reads
    # the `decisions` envelope on PostListResponse.
    # The original comment's plain-text preview (presenter-derived, link-URL stripped).
    content_preview: str | None
    link_preview: LinkPreviewResponse | None
    comment_count: int
    # presenter.whats_new.total_count: excludes the viewer's own comments and the
    # original comment, +1 for a new decision by someone else; 0 when caught up.
    new_comment_count: int
    last_commented_at: datetime | None
    # Commenters (not collaborators); the list card renders 3 + "+N" only when comment_count > 0.
    participants: list[UserResponse]
    permissions: PostPermissionsResponse


class PostShowResponse(BaseModel):
    post: PostResponse
    original_comment: PostCommentResponse | None
    top_level_comments: list[PostCommentResponse]
    # Clients diff comment.created_at and post.decided_at against this to
    # render "what's new since I was last here." Null on the first visit.
    last_visit_at: datetime | None
    mailbox_entry: PostMailboxEntryResponse | None
    subscription: SubscriptionResponse


class PostUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    content: str | None = None
    group_id: UUID | None = None
    clear_group_id: bool = False
    unfurl_links: bool = True
    attachment_claim_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str | None) -> str | None:
        # min_length=1 above checks raw length; whitespace-only titles need a
        # separate strip+reject pass to match comment-edit validation.
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be blank")
        return stripped

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("content must not be blank")
        return v

    @model_validator(mode="after")
    def at_least_one_edit(self) -> Self:
        # `model_fields_set` is too permissive — it accepts {"clear_group_id": false}
        # and {"title": null} as valid PATCH bodies even though no field is actually
        # changing. Require at least one field that the handler will act on.
        has_edit = (
            self.title is not None or self.content is not None or self.group_id is not None or self.clear_group_id
        )
        if not has_edit:
            raise ValueError("must set at least one field")
        return self

    @model_validator(mode="after")
    def no_conflicting_group_fields(self) -> Self:
        # Sending both group_id and clear_group_id silently ignores one. Reject so
        # the client knows it sent an ambiguous request.
        if self.group_id is not None and self.clear_group_id:
            raise ValueError("cannot set group_id and clear_group_id simultaneously")
        return self


# PATCH /api/posts/{id}/pin — body carries the target state explicitly so the
# call is idempotent and self-describing (no toggling inferred from the verb).
class PostPinUpdateRequest(BaseModel):
    pinned: bool


#
# Post index/list models
#
# Published posts (GET /api/posts) and drafts (GET /api/posts/drafts) are separate
# collections — different shapes, so each endpoint's cursor paginates one list.


class PostDraftResponse(BaseModel):
    id: str
    title: str
    # Client derives "Shared with me" = creator.id != current_user.id.
    creator: UserResponse
    collaborators: list[UserResponse]
    updated_at: datetime


class PostListDecisionResponse(BaseModel):
    # The index card's decision badge, kept off PostResponse: a post is decided
    # when its workspace holds a decision (posts can carry several).
    post_id: str
    # Total decisions on the post; the card shows "{count} decisions" when >1,
    # else the single preview below.
    count: int
    # Raw markdown of the most-recent decided comment; the client striptags+
    # truncates it (and shows it only when count == 1). null when that anchor
    # comment is deleted (the decision still stands).
    comment_preview: str | None


class PostListResponse(PaginatedResponse):
    # `next_cursor`/`has_more` paginate `posts`. The featured rail is the same
    # collection fetched with ?pinned=true, not a field here.
    posts: list[PostResponse]
    # Sparse: only decided posts in this page appear, keyed by post_id.
    decisions: list[PostListDecisionResponse]
    # Drafts-toggle badge; computed first-page-only (not cursor).
    draft_count: int


class PostDraftListResponse(PaginatedResponse):
    # `next_cursor`/`has_more` paginate `drafts`.
    drafts: list[PostDraftResponse]


class PostCreateRequest(BaseModel):
    # Mirrors PostUpdateRequest's validators — same fields, same rules.
    title: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1)
    group_id: UUID | None = None
    is_announcement: bool = False
    unfurl_links: bool = True
    attachment_claim_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be blank")
        return stripped

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


class PostDraftCreateRequest(BaseModel):
    # Drafts are blank-tolerant by design (the legacy "Create sharable draft" button
    # is formnovalidate) — a separate model from PostCreateRequest, whose min_length=1
    # would reject an empty draft.
    title: str = ""
    content: str = ""
    group_id: UUID | None = None
    is_announcement: bool = False


class PostCommentCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    parent_id: UUID | None = None
    # Default-on: matches the in-product expectation that pasting a URL unfurls.
    # Clients explicitly opt out (e.g. composer "remove preview" affordance).
    unfurl_links: bool = True
    attachment_claim_id: UUID | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


class PostCommentEditRequest(BaseModel):
    content: str = Field(min_length=1)
    unfurl_links: bool = True
    attachment_claim_id: UUID | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


#
# Workspace assignment
#
# Singleton sub-resource. GET returns the current state (assignee may be null);
# PATCH sets the assignee; DELETE clears it. The list of candidate users is
# served by /api/organization/members, not bundled into this resource.


class WorkspaceAssignmentResponse(BaseModel):
    assignee: UserResponse | None


class WorkspaceAssignmentUpdateRequest(BaseModel):
    user_id: UUID
