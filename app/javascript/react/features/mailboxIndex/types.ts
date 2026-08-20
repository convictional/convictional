import type { GoalSummary, MailboxEntryListItem, MailboxViewSummary } from "~/react/shared/types"

// The entry-list type cluster lives in shared/ so the shared mailbox-entries
// Query module and the MailboxActionBar composite (both below features/) can
// read it. Re-exported here so intra-feature imports keep resolving `../types`.
export type {
  ActiveMailboxView,
  ChatEntryDetail,
  EmailEntryDetail,
  GoalEntryDetail,
  MailboxEntry,
  MailboxEntryListItem,
  MailboxEntryListResponse,
  MailboxEntryLookupResponse,
  MailboxSort,
  MailboxView,
  MailboxViewIndexResponse,
  MailboxViewLayout,
  MailboxViewPayload,
  MailboxViewSummary,
  PostEntryDetail,
  ResourceType,
  ViewSection,
} from "~/react/shared/types"

// Response shape for `GET /api/users/{user_id}/top_goal?expand=parent`.
// `top_goal` is null when the user owns no active open goals and has no
// group goals to fall back to. `parent` is populated because the caller
// passed `?expand=parent`.
export interface TopGoalForUserResponse {
  top_goal: {
    id: string
    title: string | null
    description: string
    parent: GoalSummary | null
  } | null
}

// Wire format from the JSON `mailbox_sync` channel handler. See
// app/routers/api/mailbox_entries.py:443.
export interface MailboxSyncEntriesPayload {
  type: "entries"
  entries: MailboxEntryListItem[]
  synced_at: string
}

export interface MailboxSyncNewMessagesPayload {
  type: "new_messages"
  view_id: string
  count: number
}

export type MailboxSyncPayload = MailboxSyncEntriesPayload | MailboxSyncNewMessagesPayload

// --- Mailbox Views ---

export interface MailboxViewMutationResponse {
  view: MailboxViewSummary
  redirect_to: string
}

// --- Goal picker ---

// A goal as the "Sort by goal" picker needs it: identity, label, and the owner/group
// fields the picker sections by. Built from the /api/goals list response.
export interface GoalOption {
  id: string
  title: string
  ownerId: string | null
  groupId: string | null
  groupName: string | null
}

// --- Inbox Progress ---

export interface InboxProgressResponse {
  is_onboarding_mailbox_sync_complete: boolean
  onboarding_mailbox_sync_started_at: string | null
  has_gmail_integration: boolean
  has_calendar_integration: boolean
  is_google_authenticated: boolean
}
