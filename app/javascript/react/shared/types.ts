// Mirrors `app.routers.api.schemas.PaginatedResponse`. Every list endpoint
// returns these pagination fields alongside a resource-named array.
// Extend this interface for any list-shaped API response.
export interface PaginatedResponse {
  next_cursor: string | null
  has_more: boolean
}

// Mirrors config.enums.SubscriptionLevel. Used by both the per-resource
// SubscriptionBell (Subscription.level) and /notifications policy surfaces
// (SubscriptionPreference.default_level) — same backend enum.
export type SubscriptionLevel = "all" | "broadcasts" | "relevant_only"

export interface User {
  id: string
  display_name: string
  picture: string | null
}

// Mirrors `app.routers.api.schemas.DecisionResponse`. Decisions are
// workspace-scoped and anchor a comment polymorphically via comment_gid, so one
// shape serves every island (post, goal, document, chat, email thread).
export interface Decision {
  id: string
  comment_gid: string
  // Raw comment content; clients striptag + truncate for the summary row.
  // null means the anchor comment was deleted — render a tombstone, the
  // decision itself stands.
  comment_preview: string | null
  decided_by: User | null
  decided_at: string
}

// Mirrors `app.routers.api.schemas.DecisionListResponse`.
export interface DecisionListResponse extends PaginatedResponse {
  decisions: Decision[]
}

export interface BackNavigation {
  url: string
  label: string
}

export interface MailboxEntryResponse {
  id: string
  is_unread: boolean
  is_archived: boolean
  is_snoozed: boolean
  snoozed_until: string | null
}

// ----- Mailbox entry list -----
// The inbox list item shape (mirrors `MailboxEntryListItemResponse` in
// app/routers/api/mailbox_entries.py). Lives in shared/ (not the mailboxIndex
// feature) because the shared mailbox-entries Query module reads it and the
// MailboxActionBar composite navigates the list — both sit below features/, so
// features/ can't own the type. features/mailboxIndex/types.ts re-exports these.

export type MailboxView = "inbox" | "unread" | "archived" | "sent" | "drafts" | "assigned_to_me" | "snoozed"

export type MailboxSort = "newest" | "oldest"

export type ResourceType = "Chat" | "EmailThread" | "Post" | "Goal"

export interface EmailEntryDetail extends EventPreviewDetail {
  // Email is the asymmetric three-way: "message" rides the top-level `preview` string (a mail
  // snippet), "comment" rides last_comment as a chip, "activity" pins event_* like posts/goals.
  sender_display: string
  message_count: number
  attachment_count: number
  preview_kind: "message" | "comment" | "activity"
  scheduled_for: string | null
}

export interface ChatEntryDetail {
  is_group_chat: boolean
  is_dm: boolean
  collaborator_count: number
  counterparty: User | null
  last_message_author: User | null
  member_avatars: User[]
  overflow_count: number
  // The message preview rides last_comment + last_comment_author_name ("Alice: hey"). When a
  // chat-level event (member added/removed, rename) is newer than the last message, preview_kind is
  // "activity" and the raw event fields are phrased client-side (see chatActivityPreview).
  preview_kind: "comment" | "activity"
  last_comment: string | null
  last_comment_author_name: string | null
  event_action: EventAction | null
  event_details: Record<string, unknown> | null
  event_actor: User | null
}

// Mirrors config.enums.EventAction. The raw workspace-event action the server ships on an inbox
// row's `event_action`; the client phrases it (see postActivityPreview / goalActivityPreview).
export type EventAction =
  // Post events
  | "post_created"
  | "post_announced"
  | "post_commented"
  | "post_pinned"
  | "post_decided"
  // Collaboration events
  | "added_collaborator"
  | "removed_collaborator"
  | "requested_collaborator_access"
  | "commented"
  | "email_thread_comment_edited"
  | "email_thread_comment_deleted"
  // Email draft events
  | "draft_scheduled"
  | "draft_unscheduled"
  // Goal events
  | "goal_created"
  | "goal_updated"
  | "goal_closed"
  | "goal_reactivated"
  | "goal_activated"
  | "goal_completed"
  | "goal_deleted"
  | "goal_commented"
  | "goal_update_posted"
  | "goal_update_requested"
  // Meeting events
  | "meeting_updated"
  | "meeting_deleted"
  | "meeting_processed"
  | "meeting_agenda_updated"
  // Document events
  | "document_commented"
  // Workspace events
  | "updated_sharing"
  | "assigned"
  | "unassigned"
  | "decided"
  // Chat events
  | "chat_message_created"
  | "chat_message_edited"
  | "chat_message_deleted"
  | "chat_collaborator_added"
  | "chat_collaborator_removed"
  | "chat_renamed"

// The second inbox line, summarizing the resource's newest workspace event. Authored events (a
// comment, or a goal's posted update) carry their text in `last_comment` with `last_comment_author`;
// every other event ships raw — `event_action` + `event_details` (the raw Event diff) + `event_actor`
// (who did it) — for the client to phrase itself. `preview_kind` (declared per resource, since goals
// add an "update" kind) tells the client which shape a given row is. Mirrors `_EventPreviewFields`.
export interface EventPreviewDetail {
  last_comment: string | null
  last_comment_author: User | null
  event_action: EventAction | null
  event_details: Record<string, unknown> | null
  event_actor: User | null
}

export interface PostEntryDetail extends EventPreviewDetail {
  // creator_name / group_name form the title-line byline ("by @X for @Y"). is_announcement /
  // is_decided are chips on the title line. Posts have no authored "update" kind (unlike goals),
  // so preview_kind is just comment vs activity.
  creator_name: string
  group_name: string | null
  is_announcement: boolean
  is_decided: boolean
  preview_kind: "comment" | "activity"
}

export interface GoalEntryDetail extends EventPreviewDetail {
  // Evergreen goal state (status/progress/completion). "comment" and "update" are both authored
  // (avatar + last_comment, styled differently); the description rides the entry `preview` (shown
  // in a tooltip on the title).
  status: string
  is_completed: boolean
  progress: number | null
  preview_kind: "comment" | "update" | "activity"
}

export interface MailboxEntryListItem {
  id: string
  resource_type: ResourceType
  href: string
  title: string | null
  preview: string | null
  sender_display: string | null
  last_activity_at: string
  is_unread: boolean
  is_archived: boolean
  is_snoozed: boolean
  snoozed_until: string | null
  is_assigned_to_me: boolean
  is_shared: boolean
  email: EmailEntryDetail | null
  chat: ChatEntryDetail | null
  post: PostEntryDetail | null
  goal: GoalEntryDetail | null
}

export interface MailboxEntryListResponse extends PaginatedResponse {
  entries: MailboxEntryListItem[]
  synced_at: string
}

// Local-only fields layered onto the server response. Used to keep optimistic
// mutations from being clobbered by an in-flight channel sync — see the
// channel-merge rule in useMailboxEntries.
export interface MailboxEntry extends MailboxEntryListItem {
  mutatedAt?: number
}

// ----- Mailbox views (focus modes) -----
// Lives in shared/ so the canonical mailbox-view-order Query module and the
// MailboxActionBar composite (both below features/) can read it. The
// mailboxIndex feature re-exports these from `../types`.

export interface MailboxEntryLookupResponse extends PaginatedResponse {
  entries: MailboxEntryListItem[]
}

// Mirrors `config.enums.MailboxViewLayout`. "grouped" = a custom view (LLM sections);
// "ranked" = a custom sort (one flat, score-ordered list). Clients split lists by this.
export type MailboxViewLayout = "grouped" | "ranked"

export interface ViewSection {
  title: string
  description: string
  mailbox_entry_ids: string[]
  goal: GoalSummary | null
}

export interface MailboxViewSummary {
  id: string
  title: string
  view_request: string
  layout: MailboxViewLayout
  created_at: string
}

export interface ActiveMailboxView {
  kind: "template" | "view"
  // `id` and `channel_id` carry the same opaque identifier — `template:<name>` for
  // templates, bare UUID for saved views. See api/mailbox_views.py.
  id: string
  title: string | null
  view_request: string | null
  channel_id: string
  requires_goals: boolean
  // "grouped" renders LLM sections; "ranked" renders one flat score-ordered list.
  layout: MailboxViewLayout
}

export interface MailboxViewIndexResponse {
  all_views: MailboxViewSummary[]
  active: ActiveMailboxView | null
  cached_sections: ViewSection[] | null
  cached_entry_ids: string[]
  // True when cached_sections is a partial ordering still being generated (a refresh landed
  // mid-sort). Render it, but keep the spinner + channel subscription and reconcile on `complete`.
  generating: boolean
  has_goals_for_view: boolean
  is_not_found: boolean
  // Coverage transparency: considered <= eligible inbox counts; both null when no view is active.
  eligible_entry_count: number | null
  considered_entry_count: number | null
}

// Wire format from the JSON `mailbox_view` channel handler. See
// app/routers/api/mailbox_views.py.
export type MailboxViewPayload =
  | { type: "section"; section_index: number; section: ViewSection }
  | { type: "complete" }
  | { type: "error"; message: string }
  | { type: "cache_expired" }
  | { type: "regenerating"; attempt: number }
  | { type: "new_messages"; count: number; view_id: string | null }
  // Ranked sorts stream one score per candidate; `entries_scored` is the batched
  // sentinel tail (every candidate the LLM never scored) in a single frame. `rank`/`ranks`
  // carry the server's recency ordinal so the client tie-breaks equal scores identically.
  | { type: "entry_scored"; entry_id: string; score: number; rank: number }
  | { type: "entries_scored"; entry_ids: string[]; ranks: number[]; score: number }

export interface ReactionUser {
  id: string
  display_name: string
}

export interface Group {
  id: string
  name: string
}

// Mirrors `app.routers.api.schemas.OrganizationMembersResponse`. Served by
// GET /api/organization/members and cached by the organizationMembers store.
export interface OrganizationMembersResponse {
  users: User[]
  groups: Group[]
}

// Per-collaborator view state on a workspace (mirrors CollaboratorViewStateResponse in
// app/routers/api/schemas.py). last_viewed_event_id is the caught-up cursor.
export interface CollaboratorViewState {
  viewed: boolean
  last_viewed_at: string | null
  last_viewed_event_id: string | null
}

export interface Collaborator {
  id: string
  user: User
  is_removable: boolean
  status: "approved" | "pending"
  view_state: CollaboratorViewState
}

// A non-collaborator viewer (org member who opened an org-shared resource) with a recorded visit.
// Seen-by reads collaborators + viewers so casual viewers still appear in others' "Seen by".
export interface WorkspaceViewer {
  user: User
  view_state: CollaboratorViewState
}

// The workspace collaborators payload — the single cached source of collaborator roster +
// view state (see shared/hooks/useWorkspaceCollaboratorsQuery), kept live by the
// workspace_collaborators channel.
export interface WorkspaceCollaboratorsData {
  collaborators: Collaborator[]
  pending: Collaborator[]
  // Visitors who aren't approved collaborators — merged with collaborators to build "Seen by".
  viewers: WorkspaceViewer[]
  present_user_ids: string[]
  // The requesting user's own view state, present even when they aren't a collaborator — anchors
  // the goal "New activity" divider for org members viewing an organization-shared goal.
  current_user_view_state: CollaboratorViewState
}

export interface GroupMatch {
  id: string
  name: string
}

// Mirrors `app.routers.api.goals.GoalSummary`. Used wherever a goal is
// referenced from another resource (as a subgoal, as a parent, etc.).
export interface GoalSummary {
  id: string
  workspace_id: string
  title: string | null
  description: string
  status: string
  progress: number | null
  target_date: string | null
  is_completed: boolean
  is_closed: boolean
  is_draft: boolean
  owner: User | null
  group: Group | null
  open_comment_count: number
}

// Mirrors `app.routers.api.goals.GoalResponse`. `parent` and `subgoals` are
// expansions: `null` means the caller did not request `?expand=parent` or
// `?expand=subgoals`. Use `parent_id` to identify the parent without paying
// the expansion cost.
export interface Goal {
  id: string
  workspace_id: string
  title: string | null
  description: string
  status: string
  progress: number | null
  target_date: string | null
  start_date: string | null
  is_completed: boolean
  is_closed: boolean
  is_draft: boolean
  planning_list_name: string | null
  created_at: string
  owner: User | null
  group: Group | null
  open_comment_count: number
  parent_id: string | null
  parent: GoalSummary | null
  subgoals: GoalSummary[] | null
}

export interface LinkPreviewFile {
  file_name: string
  content_type: string | null
  byte_size: number | null
}

export interface LinkPreview {
  url: string
  type: "link" | "video"
  title: string | null
  description: string | null
  image_url: string | null
  site_name: string | null
  domain: string
  // The internal resource kind (goal/post/document/file/…) when this links to another
  // Convictional resource; null/absent for external links.
  resource_kind?: string | null
  // Display metadata for a pasted attachment link (resource_kind === "file"); null otherwise.
  file?: LinkPreviewFile | null
}

export interface ReplyPreview {
  id: string
  user_name: string
  content_preview: string
  is_deleted: boolean
}

export type ChatType = "dm" | "multi" | "group" | "self"

export interface ChatMessage {
  id: string
  // gid://convictional/ChatMessage/<id>; anchors a decision to this message.
  global_id: string
  content: string
  created_at: string
  edited_at: string | null
  reactions: Record<string, ReactionUser[]>
  user: User
  link_preview: LinkPreview | null
  reply_to: ReplyPreview | null
}

export interface MessageListResponse extends PaginatedResponse {
  messages: ChatMessage[]
}

// Mirrors `app.routers.api.chats.MessageWindowResponse`. Returned by the
// "around a message" endpoint: a bounded window centered on the anchor.
// next_cursor/has_more describe the older direction so loadMore keeps working.
// at_tail is true when the window's newest message IS the live tail; when false
// the client forward-paginates (loadNewer) to close the gap.
export interface MessageWindowResponse extends MessageListResponse {
  at_tail: boolean
}

export interface ChatCollaborator {
  id: string
  user: User
}

export interface ChatMetadata {
  chat_id: string
  workspace_id: string
  chat_title: string
  type: ChatType
  is_group_chat: boolean
  group_id: string | null
  collaborators: ChatCollaborator[]
  // Whether this chat supports @-mentions (multi/group chats do; dm/self don't).
  supports_mentions: boolean
  last_read_at: string | null
  unread_message_count: number
  mailbox: MailboxEntryResponse | null
}

// ----- Email thread show -----
// Mirrors the Pydantic schemas defined alongside the JSON API in
// app/routers/api/schemas.py.

export interface EmailMessageAttachment {
  id: string
  filename: string
  content_type: string | null
  is_inline: boolean
  download_url: string
  show_in_list: boolean
}

export interface EmailMessageHeader {
  name: string
  value: string
}

// Metadata-only message shape used by the thread timeline and the new-message
// broadcast. Mirrors `EmailMessageSummaryResponse`. The body, attachments, and raw
// headers are a sub-resource fetched on demand from content_url — see
// EmailMessageContentResponse (and EmailMessage for the full detail shape).
export interface EmailMessageSummary {
  id: string
  message_type: string
  subject: string | null
  raw_sender: string | null
  sender_name: string
  sender_email: string
  to: string[]
  cc: string[]
  bcc: string[]
  preview: string | null
  received_at: string | null
  sent_at: string | null
  created_at: string
  external_thread_id: string | null
  message_id: string | null
  content_url: string
  reply_url: string
  forward_url: string
  view_original_url: string
}

// The fully-materialized message, returned by the detail endpoint
// (GET /api/email_threads/{}/email_messages/{}). Mirrors `EmailMessageResponse`.
// Lists use the leaner EmailMessageSummary instead.
export interface EmailMessage extends EmailMessageSummary {
  // Null for messages that render collapsed on load — the timeline skips
  // sanitizing their HTML (a CPU-bound, event-loop-blocking step that, across a
  // long thread, can trip the worker timeout) and the body is fetched lazily via
  // content_url on expand. See the matching comment in app/routers/api/schemas.py.
  content_html: string | null
  body_plain: string | null
  // Raw, unsanitized HTML. Only populated by the detail endpoint — see the
  // matching comment in app/routers/api/schemas.py.
  body_html: string | null
  headers: EmailMessageHeader[]
  // Requires a per-message file read, so only the detail endpoint populates it.
  raw_data: Record<string, unknown> | null
  attachments: EmailMessageAttachment[]
}

// Structured activity-event payload, discriminated on `details.type`. Mirrors
// the EmailThreadEvent* detail models in app/routers/api/schemas.py.
export type EmailThreadEventDetails =
  | { type: "assigned" | "unassigned"; subject_label: string | null }
  | { type: "added_collaborator"; subject_label: string | null; reason: string | null }

export interface EmailThreadEvent {
  id: string
  action: string
  created_at: string
  creator: User | null
  // null when the action carries no renderable detail (e.g. removed_collaborator),
  // in which case the timeline renders nothing for it.
  details: EmailThreadEventDetails | null
}

export interface EmailThreadComment {
  id: string
  // GlobalID (gid://convictional/EmailThreadComment/<uuid>) used to anchor a decision to this comment.
  global_id: string
  content: string
  user: User | null
  created_at: string
  updated_at: string
  reactions: Record<string, ReactionUser[]>
  // Lean four-field link preview shared with post comments (PostCommentLinkPreview).
  link_preview: PostCommentLinkPreview | null
  attachments: EmailMessageAttachment[]
  // The comment this one quote-replies to, if any. A soft-deleted target still
  // loads, surfacing as a tombstone via is_deleted.
  reply_to: ReplyPreview | null
}

// Discriminated union via `type`. `item_id` and `created_at` are present on
// both branches so the renderer can key/sort without unwrapping `message` or
// `event`.
export type TimelineItem =
  | { type: "message"; item_id: string; created_at: string; message: EmailMessageSummary; event: null }
  | { type: "event"; item_id: string; created_at: string; message: null; event: EmailThreadEvent }

export interface EmailThreadCreator {
  id: string
  display_name: string
}

export interface EmailThreadDetail {
  id: string
  title: string
  workspace_id: string
  creator: EmailThreadCreator
  can_reply: boolean
  is_shared: boolean
  own_thread_id: string | null
}

// Mirrors `EmailThreadMailboxEntryResponse`.
export interface EmailThreadMailboxEntry {
  id: string
  is_unread: boolean
  is_archived: boolean
  is_snoozed: boolean
  snoozed_until: string | null
  is_ai_excluded: boolean
  is_shared: boolean
  read_at: string | null
}

export interface EmailThreadDraft {
  message_id: string
  composer_url: string
}

export interface EmailThreadShowResponse {
  thread: EmailThreadDetail
  mailbox_entry: EmailThreadMailboxEntry
  timeline: TimelineItem[]
  comments: EmailThreadComment[]
  draft: EmailThreadDraft | null
  last_event_id: string | null
}

export interface EmailMessageContentResponse {
  content_html: string
  body_plain: string | null
  attachments: EmailMessageAttachment[]
}

// Mirrors `EmailMessageContentItem`. Carries the message id so a batch response can be
// mapped back to its timeline message.
export interface EmailMessageContentItem extends EmailMessageContentResponse {
  id: string
}

// Mirrors `EmailMessageContentListResponse`. Batch peer of the per-message content
// endpoint — the client fetches the bodies of the messages it renders expanded on load
// in a single request rather than one request per message.
export interface EmailMessageContentListResponse extends PaginatedResponse {
  contents: EmailMessageContentItem[]
}

// Mirrors `config.enums.Sharing`. The server uses one enum for documents,
// goals, content, and workspaces; the client mirrors that — not a per-
// resource type — so a single switch covers every sharing-aware surface.
export type Sharing = "private" | "organization"

// ----- Documents -----
// Mirrors `DocumentShowResponse` and `DocumentContentResponse` in
// app/routers/api/documents.py. Both the documentEditor and documentShow
// islands consume the show endpoint; consolidating here prevents the field
// subsets from drifting independently.

export interface DocumentShowResponse {
  id: string
  title: string
  sharing: Sharing
  creator: User
  updated_at: string
  workspace_id: string
  is_collaborator: boolean
  is_creator: boolean
  collaborators: User[]
  collaborator_count: number
  request_access_url: string
  upload_url: string
}

export interface DocumentContentResponse {
  markdown: string
}

// Mirrors `DocumentFilter` (config.enums) — the browse list's scope selector.
export type DocumentFilter = "anyone" | "mine" | "others"

// Mirrors `DocumentListItemResponse` in app/routers/api/documents.py.
export interface DocumentListItem {
  id: string
  title: string
  author_display_name: string
  last_viewed_at: string | null
  updated_at: string
  comment_count: number
  sharing: Sharing
  collaborator_count: number
  source_url: string
}

// Mirrors `DocumentListResponse`. Lives in shared/ (not the documentsIndex
// feature) because the documents Query module reads it, and shared/ cannot
// import from features/.
export interface DocumentListResponse extends PaginatedResponse {
  documents: DocumentListItem[]
}

export interface ChatCreatedResponse {
  chat_id: string
  workspace_id: string
  type: ChatType
  name: string
  collaborators: ChatCollaborator[] | null
  recipient: User | null
  group: Group | null
  supports_mentions: boolean
}

// ----- Meetings (lists + collections) -----
// Mirrors `MeetingResponse` in app/routers/api/meetings.py — same shape used by
// show, list, and mutation endpoints.

export interface MeetingAttendeeStatus {
  display_name: string | null
  status: string | null
}

export interface MeetingCollectionRef {
  id: string
  title: string
  auto_assigned: boolean
}

export interface MeetingResponse {
  id: string
  title: string | null
  summary: string | null
  agenda: string | null

  scheduled_at: string | null
  scheduled_end_at: string | null
  is_completed: boolean
  is_upcoming: boolean
  is_happening_now: boolean
  is_recurring: boolean
  // Has a text or collaborative (live-document) agenda. The list view blanks
  // `agenda` to skip the per-row Y-doc fetch, so the agenda indicator reads
  // this flag rather than the (empty) agenda string.
  has_agenda: boolean
  // Declined by the requesting user — drives the struck-through upcoming row.
  is_declined: boolean
  is_initial_processing: boolean
  is_deleted: boolean
  did_recording_fail: boolean
  has_transcript: boolean
  has_chat_messages: boolean

  source_url: string
  workspace_id: string
  sharing: string

  recording_id: string | null
  conferencing_url: string | null

  user_attendees: User[]
  unresolved_attendees: MeetingAttendeeStatus[]

  collection: MeetingCollectionRef | null
  previous_meeting_id: string | null
  next_meeting_id: string | null
  next_meeting_scheduled_at: string | null
}

export interface MeetingListResponse extends PaginatedResponse {
  meetings: MeetingResponse[]
}

// Mirrors `MeetingCollectionListItemResponse` in
// app/routers/api/meetings_collections.py — list rows + show envelope use the
// same item shape, with the show envelope wrapping a single instance.
export interface MeetingCollectionListItem {
  id: string
  title: string
  description: string | null
  meeting_count: number
  last_meeting_at: string | null
  auto_assigned: boolean
}

export interface MeetingCollectionListResponse extends PaginatedResponse {
  collections: MeetingCollectionListItem[]
  // Count of meetings with no collection, for the "Uncategorized" pseudo row.
  uncategorized_count: number
}

// Mirrors `MeetingCollectionShowResponse` — the collection-show endpoint
// returns a page of the collection's past meetings plus the collection's own
// metadata (title/description) for the header.
export interface MeetingCollectionShowResponse extends PaginatedResponse {
  collection: MeetingCollectionListItem
  meetings: MeetingResponse[]
}

// Mirrors `CalendarResponse` in integrations/recall_ai/api.py.
export interface CalendarResponse {
  calendar_connected: boolean
  provider: "google" | "microsoft" | null
  preference: "all" | "none"
  calendar_user_id: string | null
  is_google_authenticated: boolean
}

// ----- Post show -----
// Mirrors the Pydantic schemas in app/routers/api/schemas.py — keep these
// field-for-field in sync with PostShowResponse and friends.

// Lean link-preview shape attached to a post/email comment. Distinct from the richer
// chat `LinkPreview` (which also carries type/site_name/domain) — the comment renderer
// derives the domain and fills the remaining fields when adapting to LinkPreview.
export interface PostCommentLinkPreview {
  url: string
  title: string | null
  description: string | null
  image_url: string | null
  // Internal resource kind (goal/post/document/file/…) derived from the URL server-side, or
  // null for external links. The comment renderers pass it through to LinkPreviewCard so an
  // attachment link renders as a file card, matching chat.
  resource_kind?: string | null
  // Re-resolved attachment metadata for a file preview (icon + size); null otherwise. Passed
  // through to LinkPreviewCard alongside resource_kind.
  file?: LinkPreviewFile | null
}

export interface PostComment {
  id: string
  // GlobalID used to reference this comment across resources (e.g. as a
  // decision's comment_gid). Mirrors PostCommentResponse.global_id.
  global_id: string
  content: string
  parent_id: string | null
  created_at: string
  updated_at: string
  user: User
  reactions: Record<string, ReactionUser[]>
  // Only populated on top-level comments; replies themselves carry an empty array.
  replies: PostComment[]
  link_preview: PostCommentLinkPreview | null
}

export interface PostCommentListResponse extends PaginatedResponse {
  comments: PostComment[]
}

export interface PostPermissions {
  edit: boolean
  pin: boolean
  delete: boolean
}

// The canonical post shape, mirroring `app.routers.api.schemas.PostResponse`.
// Returned everywhere a published post is — the list (`GET /api/posts`), show
// (`GET /api/posts/{id}`), and the decision/pin/update PATCH endpoints — so the
// postShow and postsIndex islands share one representation. Drafts are never
// returned here (show 404s on a draft) and carry collaborators rather than
// comment data, so they have their own `PostDraft`.
export interface Post {
  id: string
  title: string
  creator: User
  group: Group | null
  workspace_id: string
  is_announcement: boolean
  is_pinned: boolean
  pinned_at: string | null
  // No decision fields: the show island loads decisions from the decisions API;
  // the index card reads PostListResponse.decisions.
  // The original comment's plain-text preview (presenter-derived).
  content_preview: string | null
  link_preview: PostCommentLinkPreview | null
  comment_count: number
  // presenter.whats_new.total_count: excludes the viewer's own comments and the
  // original comment, +1 for a new decision by someone else; 0 when caught up.
  new_comment_count: number
  last_commented_at: string | null
  // Commenters (not collaborators); cards render 3 + "+N" only when comment_count > 0.
  participants: User[]
  permissions: PostPermissions
}

export interface PostMailboxEntry {
  id: string
  is_unread: boolean
  is_archived: boolean
  is_snoozed: boolean
  snoozed_until: string | null
}

export interface Subscription {
  wants_all: boolean
  is_explicit: boolean
}

export interface PostShowResponse {
  post: Post
  original_comment: PostComment | null
  top_level_comments: PostComment[]
  // Clients diff comment.created_at and decision.decided_at against this to
  // render "what's new since I was last here." Null on the first visit.
  last_visit_at: string | null
  mailbox_entry: PostMailboxEntry | null
  subscription: Subscription
}

export interface PostViewsGroup {
  id: string
  name: string
  seen_count: number
  total_audience: number
}

export interface PostViewsTimelineEntry {
  window_start: string
  count: number
}

export interface PostViewsResponse {
  seen_count: number
  total_audience: number
  first_seen_at: string | null
  last_seen_at: string | null
  group: PostViewsGroup | null
  views: PostViewsTimelineEntry[]
}
