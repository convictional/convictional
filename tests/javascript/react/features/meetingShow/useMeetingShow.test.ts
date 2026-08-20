import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { ApiError, apiFetch } from "~/react/shared/apiFetch"

import { useMeetingShow } from "~/react/features/meetingShow/hooks/useMeetingShow"
import type { MeetingBotState, MeetingDetail } from "~/react/features/meetingShow/types"

const mockedFetch = vi.mocked(apiFetch)

function meetingDetail(overrides: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    id: "m1",
    title: "Server title",
    summary: null,
    agenda: null,
    scheduled_at: null,
    scheduled_end_at: null,
    is_completed: true,
    is_upcoming: false,
    is_happening_now: false,
    is_recurring: false,
    is_initial_processing: false,
    is_deleted: false,
    did_recording_fail: false,
    has_transcript: true,
    has_chat_messages: false,
    workspace_id: "w1",
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

const BOT: MeetingBotState = {
  bot_id: "b1",
  bot_status: "done",
  bot_sub_status: null,
  is_processing_transcript: false,
  is_recording_in_progress: false,
  is_failed: false,
  will_record: true,
  is_schedulable: true,
  is_supported_meeting_platform: true,
  has_calendar_event: true,
  status_display: "Recording complete",
  failure_reason: null,
}

// Date.now drives the per-field mutatedAt vs. fetch-baseline comparison, so the
// tests pin it explicitly rather than relying on wall-clock ordering.
let now = 1000

beforeEach(() => {
  now = 1000
  vi.spyOn(Date, "now").mockImplementation(() => now)
  mockedFetch.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

function routeFetch(meeting: () => Promise<MeetingDetail>, bot: () => Promise<MeetingBotState | null>) {
  mockedFetch.mockImplementation(((url: string) => (url.endsWith("/bot") ? bot() : meeting())) as typeof apiFetch)
}

describe("useMeetingShow", () => {
  test("loads the meeting and bot together", async () => {
    routeFetch(
      () => Promise.resolve(meetingDetail({ title: "Hello" })),
      () => Promise.resolve(BOT)
    )

    const { result } = renderHook(() => useMeetingShow("m1"))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.meeting?.title).toBe("Hello")
    expect(result.current.bot).toEqual(BOT)
    expect(result.current.error).toBe(false)
  })

  test("treats a 404 from the bot endpoint as 'no bot', not an error", async () => {
    // Text-only / uploaded-video meetings have no Recall.ai bot — a normal state.
    routeFetch(
      () => Promise.resolve(meetingDetail()),
      () => Promise.reject(new ApiError(404, { detail: "No bot" }))
    )

    const { result } = renderHook(() => useMeetingShow("m1"))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.meeting).not.toBeNull()
    expect(result.current.bot).toBeNull()
    expect(result.current.error).toBe(false)
  })

  test("sets the error flag when the meeting fetch fails", async () => {
    routeFetch(
      () => Promise.reject(new ApiError(500, { detail: "boom" })),
      () => Promise.resolve(BOT)
    )

    const { result } = renderHook(() => useMeetingShow("m1"))

    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.loading).toBe(false)
  })

  test("a local edit made during an in-flight refetch survives the server response", async () => {
    // Initial load at t=1000.
    routeFetch(
      () => Promise.resolve(meetingDetail({ title: "Server 1" })),
      () => Promise.resolve(BOT)
    )
    const { result } = renderHook(() => useMeetingShow("m1"))
    await waitFor(() => expect(result.current.meeting?.title).toBe("Server 1"))

    // Start a refetch at t=2000 but hold the meeting response open. The bot
    // resolves immediately; Promise.all stays pending on the meeting.
    now = 2000
    let resolveMeeting!: (m: MeetingDetail) => void
    const pending = new Promise<MeetingDetail>(res => {
      resolveMeeting = res
    })
    routeFetch(
      () => pending,
      () => Promise.resolve(BOT)
    )
    act(() => {
      void result.current.refetch()
    })

    // User edits the title locally at t=3000 — after the refetch's baseline.
    now = 3000
    act(() => result.current.applyLocalUpdate("title", "Local edit"))
    expect(result.current.meeting?.title).toBe("Local edit")

    // The slow server response (stamped as of t=2000) lands. It must not
    // clobber the newer local edit.
    now = 4000
    await act(async () => {
      resolveMeeting(meetingDetail({ title: "Server 2" }))
      await pending
    })
    expect(result.current.meeting?.title).toBe("Local edit")
  })

  test("applyServerUpdate confirms a prior optimistic edit (newer baseline wins)", async () => {
    routeFetch(
      () => Promise.resolve(meetingDetail({ title: "Server 1" })),
      () => Promise.resolve(BOT)
    )
    const { result } = renderHook(() => useMeetingShow("m1"))
    await waitFor(() => expect(result.current.meeting?.title).toBe("Server 1"))

    now = 2000
    act(() => result.current.applyLocalUpdate("title", "Optimistic"))
    expect(result.current.meeting?.title).toBe("Optimistic")

    // The PATCH response, received after the edit, echoes the saved value and
    // is allowed through because its baseline is newer than the edit stamp.
    now = 3000
    act(() => result.current.applyServerUpdate(meetingDetail({ title: "Confirmed" })))
    expect(result.current.meeting?.title).toBe("Confirmed")
  })
})
