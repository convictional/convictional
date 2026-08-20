from enum import Enum, StrEnum


class AuthenticationProvider(StrEnum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    SLACK = "slack"
    TESTING = "testing"

    @property
    def is_google(self):
        return self == AuthenticationProvider.GOOGLE

    @property
    def is_microsoft(self):
        return self == AuthenticationProvider.MICROSOFT

    @property
    def is_slack(self):
        return self == AuthenticationProvider.SLACK

    @property
    def is_testing(self):
        return self == AuthenticationProvider.TESTING


class PushProtocol(StrEnum):
    """Names the wire-level push protocol, not the gateway. Add `FCM` for Android."""

    # RFC 8030 + VAPID. endpoint is the browser-supplied relay URL.
    WEB_PUSH = "web_push"
    # Apple Push Notification service. endpoint is an opaque device token.
    APNS = "apns"


class LinkPreviewStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"


class LinkPreviewType(StrEnum):
    LINK = "link"
    VIDEO = "video"


class ChatType(StrEnum):
    DM = "dm"
    MULTI = "multi"
    GROUP = "group"
    SELF = "self"

    @property
    def is_dm(self) -> bool:
        return self is ChatType.DM

    @property
    def is_multi(self) -> bool:
        return self is ChatType.MULTI

    @property
    def is_group(self) -> bool:
        return self is ChatType.GROUP

    @property
    def is_self(self) -> bool:
        return self is ChatType.SELF


class ChannelMessageType(StrEnum):
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    SUBSCRIPTION_CONFIRMED = "subscription_confirmed"
    SUBSCRIPTION_REJECTED = "subscription_rejected"
    EVENT = "event"
    PING = "ping"
    PONG = "pong"
    LIVE_DOCUMENT_SYNC = "live_sync"
    LIVE_DOCUMENT_AWARENESS = "live_awareness"
    TYPING = "typing"
    ASSET_VERSION_INFO = "asset_version_info"
    ASSET_VERSION_CHANGED = "asset_version_changed"


class ChannelEventResource(StrEnum):
    CHAT_COLLABORATOR = "chat_collaborator"
    CHAT_MESSAGE = "chat_message"
    CHAT_TYPING = "chat_typing"
    CHATS_INDEX = "chats_index"
    DECISION = "decision"
    DOCUMENT_COMMENT = "document_comment"
    EMAIL_DRAFT = "email_draft"
    GOAL_COMMENT = "goal_comment"
    GOALS_INDEX = "goals_index"
    GOALS_PRESENCE = "goals_presence"
    GOAL_TIMELINE = "goal_timeline"
    INBOX_PROGRESS = "inbox_progress"
    MAILBOX_SYNC = "mailbox_sync"
    MAILBOX_VIEW = "mailbox_view"
    MEETING_BOT = "meeting_bot"
    EMAIL_THREAD = "email_thread"
    ORGANIZATION_MEMBERS = "organization_members"
    POST_COMMENT = "post_comment"
    POST_DRAFT_COMMENT = "post_draft_comment"
    RESEARCH_PROGRESS = "research_progress"
    SCHEDULED_RESEARCH = "scheduled_research"
    SCHEDULED_RESEARCH_PREVIEW = "scheduled_research_preview"
    WORKSPACE_COLLABORATORS = "workspace_collaborators"
    EMAIL_THREAD_COMMENT = "email_thread_comment"
    WORKSPACE_EVENT = "workspace_event"


class ChannelEventAction(StrEnum):
    ADDED = "added"
    ARCHIVED = "archived"
    ASSIGNMENT_CHANGED = "assignment_changed"
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    DRAFT_STARTED = "draft_started"
    DRAFT_UPDATED = "draft_updated"
    DRAFT_REMOVED = "draft_removed"
    DRAFT_SCHEDULED = "draft_scheduled"
    DRAFT_UNSCHEDULED = "draft_unscheduled"
    MESSAGE_ADDED = "message_added"
    REMOVED = "removed"
    RESOLVED = "resolved"
    REACTION_TOGGLED = "reaction_toggled"
    PANEL_UPDATED = "panel_updated"
    DECISIONS_CHANGED = "decisions_changed"
    VIEW_STATE_CHANGED = "view_state_changed"
    NEW_MESSAGE = "new_message"
    UPDATED_MESSAGE = "updated_message"
    DELETED_MESSAGE = "deleted_message"
    TYPING = "typing"


class CollaboratorStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"

    @property
    def is_pending(self):
        return self == CollaboratorStatus.PENDING

    @property
    def is_approved(self):
        return self == CollaboratorStatus.APPROVED


class IntegrationConnectionStatus(StrEnum):
    # Explicit, mutually-exclusive connection state rather than a bag of booleans.
    # "unavailable" means the user's sign-in method (e.g. Microsoft SSO)
    # can't connect a Google-backed integration at all — distinct from a Google user
    # who simply hasn't connected yet. Shared home (config is below both app and
    # integrations) so the Gmail and onboarding APIs use one definition.
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNAVAILABLE = "unavailable"


class CommandType(StrEnum):
    QUICK_LINK = "quick_link"
    RESEARCH = "research"
    CREATE_QUICK_LINK = "create_quick_link"

    @property
    def is_quick_link(self):
        return self == CommandType.QUICK_LINK

    @property
    def is_research(self):
        return self == CommandType.RESEARCH

    @property
    def is_create_quick_link(self):
        return self == CommandType.CREATE_QUICK_LINK


class ResearchSource(StrEnum):
    INTERNAL = "internal"
    SLACK = "slack"


class ContentCategory(StrEnum):
    DOCUMENT = "document"
    ACTIVITY = "activity"
    PERSON = "person"


class ContentType(StrEnum):
    MEETING = "meeting"
    MEETING_TRANSCRIPT = "meeting_transcript"
    POST = "post"
    POST_COMMENT = "post_comment"
    GOAL_COMMENT = "goal_comment"
    USER = "user"
    EMAIL_CONTACT = "email_contact"
    DOCUMENT = "document"
    GOAL = "goal"
    DECISION = "decision"

    FILE = "file"
    EMAIL_THREAD = "email_thread"
    SLACK_MESSAGE = "slack_message"
    CHAT = "chat"
    CHAT_HISTORY = "chat_history"


class AccessAction(StrEnum):
    ADD = "add"
    REMOVE = "remove"


class CloseableStatusFilter(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class DocumentFilter(StrEnum):
    ANYONE = "anyone"
    MINE = "mine"
    OTHERS = "others"


class PostStatusFilter(StrEnum):
    OPEN = "open"
    DRAFTS = "drafts"


class MailboxLabel(StrEnum):
    INBOX = "inbox"
    UNREAD = "unread"


class EmailMailboxLabel(StrEnum):
    SENT = "sent"
    DRAFT = "draft"
    SPAM = "spam"


class EmailLabel(StrEnum):
    INBOX = "inbox"
    SENT = "sent"
    DRAFT = "draft"
    SPAM = "spam"
    UNREAD = "unread"


class EmailMessageType(StrEnum):
    RECEIVED = "received"
    SENT = "sent"
    DRAFT = "draft"
    SENDING = "sending"


class EmailReplyType(StrEnum):
    REPLY = "reply"
    REPLY_ALL = "reply_all"

    @property
    def is_reply(self):
        return self == EmailReplyType.REPLY

    @property
    def is_reply_all(self):
        return self == EmailReplyType.REPLY_ALL


class EmailDraftAction(StrEnum):
    ASSIGNMENT_CHANGED = "assignment_changed"
    DRAFT_STARTED = "draft_started"
    DRAFT_UPDATED = "draft_updated"
    DRAFT_REMOVED = "draft_removed"
    DRAFT_SCHEDULED = "draft_scheduled"
    DRAFT_UNSCHEDULED = "draft_unscheduled"


class MailboxSort(StrEnum):
    NEWEST = "newest"
    OLDEST = "oldest"


class MailboxViewLayout(StrEnum):
    GROUPED = "grouped"
    RANKED = "ranked"

    @property
    def is_ranked(self) -> bool:
        return self is MailboxViewLayout.RANKED


class MailboxViewName(StrEnum):
    INBOX = "inbox"
    UNREAD = "unread"
    ARCHIVED = "archived"
    SENT = "sent"
    DRAFTS = "drafts"
    ASSIGNED_TO_ME = "assigned_to_me"
    SNOOZED = "snoozed"

    @property
    def is_inbox(self) -> bool:
        return self is MailboxViewName.INBOX

    @property
    def is_archived(self) -> bool:
        return self is MailboxViewName.ARCHIVED

    @property
    def is_sent(self) -> bool:
        return self is MailboxViewName.SENT

    @property
    def is_drafts(self) -> bool:
        return self is MailboxViewName.DRAFTS

    @property
    def is_assigned_to_me(self) -> bool:
        return self is MailboxViewName.ASSIGNED_TO_ME

    @property
    def is_snoozed(self) -> bool:
        return self is MailboxViewName.SNOOZED


class EventAction(StrEnum):
    # Post events
    POST_CREATED = "post_created"
    POST_ANNOUNCED = "post_announced"
    POST_COMMENTED = "post_commented"
    POST_PINNED = "post_pinned"
    POST_DECIDED = "post_decided"

    # Collaboration events
    ADDED_COLLABORATOR = "added_collaborator"
    REMOVED_COLLABORATOR = "removed_collaborator"
    REQUESTED_COLLABORATOR_ACCESS = "requested_collaborator_access"
    COMMENTED = "commented"
    EMAIL_THREAD_COMMENT_EDITED = "email_thread_comment_edited"
    EMAIL_THREAD_COMMENT_DELETED = "email_thread_comment_deleted"

    # Email draft events
    DRAFT_SCHEDULED = "draft_scheduled"
    DRAFT_UNSCHEDULED = "draft_unscheduled"

    # Goal events
    GOAL_CREATED = "goal_created"
    GOAL_UPDATED = "goal_updated"
    GOAL_CLOSED = "goal_closed"
    GOAL_REACTIVATED = "goal_reactivated"
    GOAL_ACTIVATED = "goal_activated"
    GOAL_COMPLETED = "goal_completed"
    GOAL_DELETED = "goal_deleted"
    GOAL_COMMENTED = "goal_commented"
    GOAL_UPDATE_POSTED = "goal_update_posted"
    GOAL_UPDATE_REQUESTED = "goal_update_requested"

    # Meeting events
    MEETING_UPDATED = "meeting_updated"
    MEETING_DELETED = "meeting_deleted"
    MEETING_PROCESSED = "meeting_processed"
    MEETING_AGENDA_UPDATED = "meeting_agenda_updated"

    # Document events
    DOCUMENT_COMMENTED = "document_commented"

    # Workspace events
    UPDATED_SHARING = "updated_sharing"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    DECIDED = "decided"

    # Chat events. Message create/edit/delete are data-only (the preview reads the message live);
    # member add/remove and rename drive the inbox "activity" line (see ChatMailboxEntry).
    CHAT_MESSAGE_CREATED = "chat_message_created"
    CHAT_MESSAGE_EDITED = "chat_message_edited"
    CHAT_MESSAGE_DELETED = "chat_message_deleted"
    CHAT_COLLABORATOR_ADDED = "chat_collaborator_added"
    CHAT_COLLABORATOR_REMOVED = "chat_collaborator_removed"
    CHAT_RENAMED = "chat_renamed"


class FlashLevel(Enum):
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class GoalStatus(StrEnum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"


class HTMLSwap(StrEnum):
    OUTER_HTML = "outer_html"
    INNER_HTML = "inner_html"
    BEFORE_BEGIN = "before_begin"
    BEFORE_END = "before_end"
    AFTER_BEGIN = "after_begin"
    REMOVE = "remove"
    MORPH = "morph"


class Integration(StrEnum):
    GMAIL = "gmail"
    NOTION = "notion"
    RECALL_AI_CALENDAR = "recall_ai_calendar"
    SLACK = "slack"

    @property
    def is_gmail(self):
        return self == Integration.GMAIL

    @property
    def is_notion(self):
        return self == Integration.NOTION

    @property
    def is_recall_ai_calendar(self):
        return self == Integration.RECALL_AI_CALENDAR

    @property
    def is_slack(self):
        return self == Integration.SLACK


class JobQueue(StrEnum):
    UI = "ui"
    EMAIL = "email"
    PUSH = "push"
    INDEXING = "indexing"
    MISCELLANEOUS = "miscellaneous"
    ONBOARDING_SYNC = "onboarding-sync"
    MAINTENANCE = "maintenance"

    @property
    def cloud_tasks_queue_name(self):
        return f"convictional-{self.value}"


class JobStatus(StrEnum):
    SCHEDULED = "scheduled"
    ENQUEUED = "enqueued"
    STARTED = "started"
    FAILED = "failed"
    SUCCESSFUL = "success"
    TERMINATED = "terminated"
    DEAD = "dead"

    @property
    def is_busy(self):
        return self in [JobStatus.ENQUEUED, JobStatus.STARTED]


class JumpToField(StrEnum):
    TITLE = "title"
    AUTHOR = "author"


class LLMMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class LLMBlockType(StrEnum):
    TEXT = "text"
    TOOL_USE = "tool_use"


class LLMChunkType(StrEnum):
    CONTENT_BLOCK_START = "content_block_start"
    CONTENT_BLOCK_DELTA = "content_block_delta"
    CONTENT_BLOCK_STOP = "content_block_stop"


class LLMChunkDeltaType(StrEnum):
    TEXT_DELTA = "text_delta"
    INPUT_JSON_DELTA = "input_json_delta"


class MeetingCollectionFilter(StrEnum):
    MOST_RECENT = "most_recent"
    UNCATEGORIZED = "uncategorized"


class MeetingCollectionAction(StrEnum):
    EXISTING = "existing"
    NEW = "new"
    NONE = "none"


class MeetingAttendeeStatus(StrEnum):
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"
    NOT_AVAILABLE = "not_available"


class MeetingChatMessageSenderPlatform(StrEnum):
    MOBILE_APP = "mobile_app"
    DESKTOP = "desktop"
    DIAL_IN = "dial_in"
    UNKNOWN = "unknown"


class EmailDelivery(StrEnum):
    SEND = "send"
    SKIP = "skip"

    @property
    def is_send(self):
        return self == EmailDelivery.SEND

    @property
    def is_skip(self):
        return self == EmailDelivery.SKIP


class DeliveryChannel(StrEnum):
    EMAIL = "email"
    PUSH = "push"


class RecordModelEvent(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class ResearchQuestionStatus(StrEnum):
    PENDING = "pending"
    STARTED = "started"
    COMPLETED = "completed"

    @property
    def is_pending(self):
        return self == ResearchQuestionStatus.PENDING

    @property
    def is_started(self):
        return self == ResearchQuestionStatus.STARTED

    @property
    def is_completed(self):
        return self == ResearchQuestionStatus.COMPLETED


class ScheduledResearchFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    WEEKDAYS = "weekdays"


class ReactionType(StrEnum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    TEARS_OF_JOY = "tears_of_joy"
    PARTY_POPPER = "party_popper"
    FROWNING_FACE = "frowning_face"
    HEART = "heart"
    ROCKET = "rocket"
    EYES = "eyes"


class SignupReason(StrEnum):
    WITH_TEAM = "I have a current decision I want to work through with my team"
    COMMUNICATE_TO_TEAM = "I have a decision I want to work through alone and then communicate to my team"
    DECIDED_BY_TEAM = "I have a decision I want to propose for someone on my team to decide"
    INVITED = "I was invited by someone else at my organization"
    CURIOUS = "Just curious about Convictional"
    OTHER = "Something else"


class SignalStrength(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class Sharing(StrEnum):
    PRIVATE = "private"
    ORGANIZATION = "organization"

    @property
    def is_private(self):
        return self == Sharing.PRIVATE

    @property
    def is_organization(self):
        return self == Sharing.ORGANIZATION


class SubscriptionLevel(StrEnum):
    ALL = "all"
    BROADCASTS = "broadcasts"
    RELEVANT_ONLY = "relevant_only"


class SubscriptionSource(StrEnum):
    RESOURCE = "resource"
    CREATOR = "creator"
    GROUP_MEMBERSHIP = "group_membership"
    GLOBAL = "global"
    NONE = "none"


class UpdateFrequency(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @property
    def is_weekly(self):
        return self == UpdateFrequency.WEEKLY

    @property
    def is_monthly(self):
        return self == UpdateFrequency.MONTHLY


class ContactsSyncStatus(StrEnum):
    RATE_LIMITED = "rate_limited"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    ERROR = "error"
    SUCCESS = "success"


# Note: Please preserve alphabetical order when adding new enums to this file.
