import type {
  MeetingCollectionListItem,
  MeetingCollectionListResponse,
  MeetingCollectionShowResponse,
  MeetingListResponse,
  MeetingResponse,
} from "~/react/shared/types"

export function makeMeeting(overrides: Partial<MeetingResponse> = {}): MeetingResponse {
  return {
    id: "meeting-1",
    title: "Standup",
    summary: null,
    agenda: "",
    scheduled_at: "2026-06-09T15:00:00Z",
    scheduled_end_at: "2026-06-09T15:30:00Z",
    is_completed: false,
    is_upcoming: true,
    is_happening_now: false,
    is_recurring: false,
    has_agenda: false,
    is_declined: false,
    is_initial_processing: false,
    is_deleted: false,
    did_recording_fail: false,
    has_transcript: false,
    has_chat_messages: false,
    source_url: "",
    workspace_id: "ws-1",
    sharing: "workspace",
    recording_id: null,
    conferencing_url: null,
    user_attendees: [],
    unresolved_attendees: [],
    collection: null,
    previous_meeting_id: null,
    next_meeting_id: null,
    next_meeting_scheduled_at: null,
    ...overrides,
  }
}

export function makeCollection(overrides: Partial<MeetingCollectionListItem> = {}): MeetingCollectionListItem {
  return {
    id: "col-1",
    title: "Weekly Sync",
    description: null,
    meeting_count: 0,
    last_meeting_at: null,
    auto_assigned: false,
    ...overrides,
  }
}

export function makeListPage(
  meetings: MeetingResponse[],
  pagination: Partial<Pick<MeetingListResponse, "next_cursor" | "has_more">> = {}
): MeetingListResponse {
  return { meetings, next_cursor: null, has_more: false, ...pagination }
}

export function makeShowPage(
  collection: MeetingCollectionListItem,
  meetings: MeetingResponse[],
  pagination: Partial<Pick<MeetingCollectionShowResponse, "next_cursor" | "has_more">> = {}
): MeetingCollectionShowResponse {
  return { collection, meetings, next_cursor: null, has_more: false, ...pagination }
}

export function makeCollectionListResponse(
  collections: MeetingCollectionListItem[],
  {
    uncategorized_count = 0,
    ...pagination
  }: Partial<Pick<MeetingCollectionListResponse, "next_cursor" | "has_more" | "uncategorized_count">> = {}
): MeetingCollectionListResponse {
  return { collections, uncategorized_count, next_cursor: null, has_more: false, ...pagination }
}

// A manually-resolvable promise, for asserting how a hook handles responses
// that settle out of order (the stale-response / race guards).
export function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}
