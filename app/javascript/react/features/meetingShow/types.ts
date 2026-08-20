import type { BackNavigation, MeetingCollectionRef, PaginatedResponse, Sharing } from "~/react/shared/types"

export interface MeetingShowProps {
  meetingId: string
  back: BackNavigation
}

export interface AttendeeStatus {
  display_name: string | null
  status: string | null
}

// Mirrors the API's UserResponse (app/routers/api/schemas.py) and is structurally
// the shared `User` type, so it can flow straight into <AvatarGroup>.
export interface UserAttendee {
  id: string
  display_name: string
  picture: string | null
}

// Mirrors the API's MeetingResponse (app/routers/api/meetings.py). One shape
// covers every lifecycle state — the island branches on is_upcoming to render
// the upcoming view (agenda / recording) or the completed view (recording /
// transcript), so this carries the union of both views' fields.
export interface MeetingDetail {
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
  is_initial_processing: boolean
  is_deleted: boolean
  did_recording_fail: boolean
  has_transcript: boolean
  has_chat_messages: boolean

  workspace_id: string
  sharing: Sharing

  recording_id: string | null

  conferencing_url: string | null

  user_attendees: UserAttendee[]
  unresolved_attendees: AttendeeStatus[]

  collection: MeetingCollectionRef | null
  previous_meeting_id: string | null
  next_meeting_id: string | null
  next_meeting_scheduled_at: string | null
}

export interface MeetingBotState {
  bot_id: string | null
  bot_status: string
  bot_sub_status: string | null
  is_processing_transcript: boolean
  is_recording_in_progress: boolean
  is_failed: boolean
  will_record: boolean
  is_schedulable: boolean
  is_supported_meeting_platform: boolean
  has_calendar_event: boolean
  status_display: string
  failure_reason: string | null
}

export interface MeetingChatMessage {
  sender_name: string
  text: string
  created_at: string
}

export interface MeetingChatListResponse extends PaginatedResponse {
  messages: MeetingChatMessage[]
}

export type TabKey = "summary" | "agenda"

export interface TranscriptLine {
  line_number: number
  speaker: string | null
  content: string
  start_time: number | null
  end_time: number | null
}

export interface ProcessedTranscript {
  lines: TranscriptLine[]
}

export interface MeetingRecording {
  id: string
  url: string
}

// Signed direct-upload target from POST /api/meetings/{id}/recording/upload_url.
// `fields` are opaque form fields the client must POST verbatim alongside the
// file; `key` is echoed back via PATCH recording_key once the upload completes.
export interface RecordingUploadTarget {
  action: string
  fields: Record<string, string>
  key: string
}
