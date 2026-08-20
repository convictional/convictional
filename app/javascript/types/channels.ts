export enum ChannelMessageType {
  SUBSCRIBE = "subscribe",
  UNSUBSCRIBE = "unsubscribe",
  EVENT = "event",
  SUBSCRIPTION_CONFIRMED = "subscription_confirmed",
  SUBSCRIPTION_REJECTED = "subscription_rejected",
  PING = "ping",
  LIVE_DOCUMENT_SYNC = "live_sync",
  LIVE_DOCUMENT_AWARENESS = "live_awareness",
  PONG = "pong",
  TYPING = "typing",
  ASSET_VERSION_INFO = "asset_version_info",
  ASSET_VERSION_CHANGED = "asset_version_changed",
}

export enum ChannelEventResource {
  CHAT_COLLABORATOR = "chat_collaborator",
  CHAT_MESSAGE = "chat_message",
  CHAT_TYPING = "chat_typing",
  CHATS_INDEX = "chats_index",
  DECISION = "decision",
  DOCUMENT_COMMENT = "document_comment",
  EMAIL_DRAFT = "email_draft",
  GOAL_COMMENT = "goal_comment",
  GOALS_INDEX = "goals_index",
  GOALS_PRESENCE = "goals_presence",
  GOAL_TIMELINE = "goal_timeline",
  INBOX_PROGRESS = "inbox_progress",
  MAILBOX_SYNC = "mailbox_sync",
  MAILBOX_VIEW = "mailbox_view",
  MEETING_BOT = "meeting_bot",
  EMAIL_THREAD = "email_thread",
  ORGANIZATION_MEMBERS = "organization_members",
  POST_COMMENT = "post_comment",
  POST_DRAFT_COMMENT = "post_draft_comment",
  RESEARCH_PROGRESS = "research_progress",
  SCHEDULED_RESEARCH = "scheduled_research",
  SCHEDULED_RESEARCH_PREVIEW = "scheduled_research_preview",
  WORKSPACE_COLLABORATORS = "workspace_collaborators",
  EMAIL_THREAD_COMMENT = "email_thread_comment",
  WORKSPACE_EVENT = "workspace_event",
}

/**
 * Topic stream names — the first segment of a channel's identity. Each value must
 * match a backend `@router.on_subscribe(<stream>)` key exactly; the server rejects
 * a subscribe whose stream has no registered handler. This is the canonical set the
 * frontend may subscribe to (via useChannel, useCollaboration, or subscribeTo).
 */
export enum ChannelStream {
  CHAT = "chat",
  CHATS_INDEX = "chats_index",
  DOCUMENT = "document",
  DOCUMENT_COMMENTS = "document_comments",
  EMAIL_DRAFT = "email_draft",
  EMAIL_THREAD = "email_thread",
  EMAIL_THREAD_COMMENTS = "email_thread_comments",
  EMAIL_THREAD_DRAFT = "email_thread_draft",
  GOAL_COMMENTS = "goal_comments",
  GOAL_TIMELINE = "goal_timeline",
  GOALS_INDEX = "goals_index",
  GOALS_PRESENCE = "goals_presence",
  INBOX_PROGRESS = "inbox_progress",
  MAILBOX_SYNC = "mailbox_sync",
  MAILBOX_VIEW = "mailbox_view",
  MEETING_AGENDA = "meeting_agenda",
  MEETING_BOT = "meeting_bot",
  ORGANIZATION_MEMBERS = "organization_members",
  POST_COMMENTS = "post_comments",
  POST_DRAFT = "post_draft",
  POST_DRAFT_COMMENTS = "post_draft_comments",
  RESEARCH_PROGRESS = "research_progress",
  SCHEDULED_RESEARCH = "scheduled_research",
  SCHEDULED_RESEARCH_PREVIEW = "scheduled_research_preview",
  WORKSPACE_COLLABORATORS = "workspace_collaborators",
  WORKSPACE_EVENTS = "workspace_events",
}

export enum ChannelEventAction {
  ADDED = "added",
  ARCHIVED = "archived",
  ASSIGNMENT_CHANGED = "assignment_changed",
  CREATED = "created",
  UPDATED = "updated",
  DELETED = "deleted",
  DRAFT_STARTED = "draft_started",
  DRAFT_UPDATED = "draft_updated",
  DRAFT_REMOVED = "draft_removed",
  DRAFT_SCHEDULED = "draft_scheduled",
  DRAFT_UNSCHEDULED = "draft_unscheduled",
  MESSAGE_ADDED = "message_added",
  REMOVED = "removed",
  RESOLVED = "resolved",
  REACTION_TOGGLED = "reaction_toggled",
  PANEL_UPDATED = "panel_updated",
  DECISIONS_CHANGED = "decisions_changed",
  VIEW_STATE_CHANGED = "view_state_changed",
  NEW_MESSAGE = "new_message",
  UPDATED_MESSAGE = "updated_message",
  DELETED_MESSAGE = "deleted_message",
  TYPING = "typing",
}

export interface BaseChannelMessage {
  type: ChannelMessageType
}

export interface ChannelMessage extends BaseChannelMessage {
  // A message identifies its topic by its `topic_stream` + `topic_params`.
  topic_stream?: string
  topic_params?: Record<string, string>
}

export interface SubscriptionResponse extends ChannelMessage {
  type: ChannelMessageType.SUBSCRIPTION_CONFIRMED | ChannelMessageType.SUBSCRIPTION_REJECTED
  error?: string
}

export type ChannelParams = Record<string, string | number | boolean | null | undefined>

export interface ChannelSubscription {
  // Canonical topic name — the dedup/correlation key for both subscribe forms.
  name: string
  callback: (data: WebSocketMessage) => void
  // Non-identity subscribe params (the server's SubscribeMessage.params) — e.g.
  // mailbox_sync's view_id. Not part of the topic identity / dedup key.
  params?: ChannelParams
  stream?: string
  topicParams?: Record<string, string>
}

export interface SubscriptionMessage extends ChannelMessage {
  type: ChannelMessageType.SUBSCRIBE | ChannelMessageType.UNSUBSCRIBE
  params?: ChannelParams
}

export interface PingMessage extends BaseChannelMessage {
  type: ChannelMessageType.PING
}

export interface PongMessage extends BaseChannelMessage {
  type: ChannelMessageType.PONG
  data: string
}

export interface TypingMessage extends ChannelMessage {
  type: ChannelMessageType.TYPING
  is_typing: boolean
}

export interface EventMessage extends ChannelMessage {
  type: ChannelMessageType.EVENT
  resource: ChannelEventResource
  action: ChannelEventAction
  data: Record<string, unknown>
}

export interface LiveDocumentSyncMessage extends ChannelMessage {
  type: ChannelMessageType.LIVE_DOCUMENT_SYNC
  data: string
  origin?: string
}

export interface LiveDocumentAwarenessMessage extends ChannelMessage {
  type: ChannelMessageType.LIVE_DOCUMENT_AWARENESS
  data: string
  origin?: string
}

export interface AssetVersionInfoMessage extends ChannelMessage {
  type: ChannelMessageType.ASSET_VERSION_INFO
  version: string
}

export interface AssetVersionChangedMessage extends ChannelMessage {
  type: ChannelMessageType.ASSET_VERSION_CHANGED
  version: string
}

export interface WebSocketMessageRegistry {
  [ChannelMessageType.SUBSCRIPTION_CONFIRMED]: SubscriptionResponse
  [ChannelMessageType.SUBSCRIPTION_REJECTED]: SubscriptionResponse
  [ChannelMessageType.SUBSCRIBE]: SubscriptionMessage
  [ChannelMessageType.UNSUBSCRIBE]: SubscriptionMessage
  [ChannelMessageType.PING]: PingMessage
  [ChannelMessageType.PONG]: PongMessage
  [ChannelMessageType.EVENT]: EventMessage
  [ChannelMessageType.LIVE_DOCUMENT_SYNC]: LiveDocumentSyncMessage
  [ChannelMessageType.LIVE_DOCUMENT_AWARENESS]: LiveDocumentAwarenessMessage
  [ChannelMessageType.TYPING]: TypingMessage
  [ChannelMessageType.ASSET_VERSION_INFO]: AssetVersionInfoMessage
  [ChannelMessageType.ASSET_VERSION_CHANGED]: AssetVersionChangedMessage
}

export type WebSocketMessage = WebSocketMessageRegistry[keyof WebSocketMessageRegistry]
