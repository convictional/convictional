import type { Goal, Group, MailboxEntryResponse, User } from "~/react/shared/types"

// The goal show endpoint returns the goal resource plus, when the page URL
// carries ?mailbox_entry_id= (goal opened from the inbox), the entry's
// read/archive/snooze state. `mailbox_entry` is null for any other arrival.
export interface GoalShowResponse extends Goal {
  mailbox_entry: MailboxEntryResponse | null
}

export interface TimelineCommentResponse {
  id: string
  content: string
  user: User | null
}

export interface TimelineGoalUpdateResponse {
  id: string
  question_text: string
  answer_text: string | null
  status: string
  progress: number | null
  requested_by: User | null
}

export interface TimelineEvent {
  id: string
  action: string
  created_at: string
  creator: User | null
  details: Record<string, unknown>
  owner: User | null
  group: Group | null
  replies: TimelineEvent[]
  comment: TimelineCommentResponse | null
  goal_update: TimelineGoalUpdateResponse | null
}

// Timeline carries only content (events). View state (seen-by / last-seen) is read
// separately from the shared collaborators query — see useWorkspaceViewState.
export interface TimelineResponse {
  events: TimelineEvent[]
}

export interface GoalUpdateSubmitData {
  status: string
  question_text: string
  answer_text: string | null
  progress: number | null
  is_draft?: boolean
}
