import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// Mock the data hook so each test drives the meeting/bot state directly, and
// stub the heavy children (network, channels, video) down to markers so these
// tests exercise only the processing/failed/ready state gate.
vi.mock("~/react/features/meetingShow/hooks/useMeetingShow", () => ({ useMeetingShow: vi.fn() }))
vi.mock("~/react/features/meetingShow/hooks/useBotStateChannel", () => ({ useBotStateChannel: vi.fn() }))
vi.mock("~/react/features/meetingShow/components/Header", () => ({ Header: () => <div>header</div> }))
vi.mock("~/react/features/meetingShow/components/Tabs", () => ({ Tabs: () => <div>content-tabs</div> }))
vi.mock("~/react/features/meetingShow/components/AttendeesPanel", () => ({ AttendeesPanel: () => <div>attendees</div> }))
vi.mock("~/react/features/meetingShow/components/VideoPlayer", () => ({ VideoPlayer: () => <div>video-player</div> }))
vi.mock("~/react/features/meetingShow/components/VideoUploadForm", () => ({
  VideoUploadForm: () => <div>upload-form</div>,
}))
vi.mock("~/react/features/meetingShow/components/CopyTimestampButton", () => ({
  CopyTimestampButton: () => <div>copy-timestamp</div>,
}))
vi.mock("~/react/features/meetingShow/components/TranscriptsToggle", () => ({
  TranscriptsToggle: () => <div>transcripts</div>,
}))
vi.mock("~/react/features/meetingShow/components/RecallStatusBadge", () => ({
  RecallStatusBadge: () => <div>bot-badge</div>,
}))
// The upcoming view is exercised by its own components' tests; here we only
// verify MeetingShow routes to it, so stub it to a marker.
vi.mock("~/react/features/meetingShow/UpcomingView", () => ({ UpcomingView: () => <div>upcoming-view</div> }))

import { MeetingShow } from "~/react/features/meetingShow/MeetingShow"
import { useMeetingShow } from "~/react/features/meetingShow/hooks/useMeetingShow"
import type { MeetingBotState, MeetingDetail } from "~/react/features/meetingShow/types"

const mockedUseMeetingShow = vi.mocked(useMeetingShow)

const BACK = { url: "/meetings", label: "Back to meetings" }

function meeting(overrides: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    id: "m1",
    title: "Standup",
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
  status_display: "Processing",
  failure_reason: null,
}

function hookValue(overrides: Partial<ReturnType<typeof useMeetingShow>> = {}): ReturnType<typeof useMeetingShow> {
  return {
    meeting: meeting(),
    bot: null,
    loading: false,
    error: false,
    applyLocalUpdate: vi.fn(),
    applyServerUpdate: vi.fn(),
    applyBotUpdate: vi.fn(),
    refetch: vi.fn(),
    ...overrides,
  }
}

afterEach(cleanup)

describe("MeetingShow state gate", () => {
  test("renders the recording-failed state without the header or video", () => {
    mockedUseMeetingShow.mockReturnValue(
      hookValue({ meeting: meeting({ has_transcript: false, did_recording_fail: true }), bot: BOT })
    )
    render(<MeetingShow meetingId="m1" back={BACK} />)

    expect(screen.getByText(/couldn't record this meeting/i)).toBeInTheDocument()
    expect(screen.getByText("bot-badge")).toBeInTheDocument()
    expect(screen.getByText("content-tabs")).toBeInTheDocument()
    expect(screen.queryByText("header")).not.toBeInTheDocument()
    expect(screen.queryByText("video-player")).not.toBeInTheDocument()
    // Even without the header, mobile users must get a way back.
    expect(screen.getByRole("link", { name: "Back to meetings" })).toHaveAttribute("href", "/meetings")
  })

  test("renders the processing state with the spinner copy, no header", () => {
    mockedUseMeetingShow.mockReturnValue(
      hookValue({ meeting: meeting({ has_transcript: false }), bot: { ...BOT, is_processing_transcript: true } })
    )
    render(<MeetingShow meetingId="m1" back={BACK} />)

    expect(screen.getByText(/done being processed/i)).toBeInTheDocument()
    expect(screen.getByText("content-tabs")).toBeInTheDocument()
    expect(screen.queryByText("header")).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Back to meetings" })).toHaveAttribute("href", "/meetings")
  })

  test("renders the unrecorded state when a completed meeting will never be processed", () => {
    // No transcript, no in-flight job, and a bot that is neither recording nor
    // transcribing — the meeting is over and nothing will advance it.
    mockedUseMeetingShow.mockReturnValue(
      hookValue({ meeting: meeting({ has_transcript: false, is_completed: true }), bot: BOT })
    )
    render(<MeetingShow meetingId="m1" back={BACK} />)

    expect(screen.getByText(/wasn't recorded/i)).toBeInTheDocument()
    expect(screen.getByText("bot-badge")).toBeInTheDocument()
    expect(screen.getByText("content-tabs")).toBeInTheDocument()
    expect(screen.queryByText("header")).not.toBeInTheDocument()
    expect(screen.queryByText(/done being processed/i)).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Back to meetings" })).toHaveAttribute("href", "/meetings")
  })

  test("renders the completed layout (header + content) when ready", () => {
    mockedUseMeetingShow.mockReturnValue(hookValue({ meeting: meeting({ has_transcript: true }), bot: BOT }))
    render(<MeetingShow meetingId="m1" back={BACK} />)

    expect(screen.getByText("header")).toBeInTheDocument()
    expect(screen.getByText("content-tabs")).toBeInTheDocument()
    // The bot badge is NOT shown on a ready meeting (HTMX shows it only while
    // processing or failed).
    expect(screen.queryByText("bot-badge")).not.toBeInTheDocument()
    expect(screen.queryByText(/done being processed/i)).not.toBeInTheDocument()
  })

  test("routes an upcoming meeting to the upcoming view, not the completed layout", () => {
    mockedUseMeetingShow.mockReturnValue(
      hookValue({ meeting: meeting({ is_upcoming: true, is_completed: false, has_transcript: false }), bot: BOT })
    )
    render(<MeetingShow meetingId="m1" back={BACK} />)

    expect(screen.getByText("upcoming-view")).toBeInTheDocument()
    // None of the completed-view branches (processing spinner, content tabs)
    // should render for an upcoming meeting.
    expect(screen.queryByText("content-tabs")).not.toBeInTheDocument()
    expect(screen.queryByText(/done being processed/i)).not.toBeInTheDocument()
  })

  test("polls refetch every 3s while processing", () => {
    vi.useFakeTimers()
    const refetch = vi.fn()
    mockedUseMeetingShow.mockReturnValue(
      hookValue({
        meeting: meeting({ has_transcript: false }),
        bot: { ...BOT, is_processing_transcript: true },
        refetch,
      })
    )
    render(<MeetingShow meetingId="m1" back={BACK} />)

    expect(refetch).not.toHaveBeenCalled()
    vi.advanceTimersByTime(9000)
    expect(refetch).toHaveBeenCalledTimes(3)
    vi.useRealTimers()
  })

  test("does not poll once the meeting is ready", () => {
    vi.useFakeTimers()
    const refetch = vi.fn()
    mockedUseMeetingShow.mockReturnValue(hookValue({ meeting: meeting({ has_transcript: true }), refetch }))
    render(<MeetingShow meetingId="m1" back={BACK} />)

    vi.advanceTimersByTime(9000)
    expect(refetch).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  test("does not poll an unrecorded meeting", () => {
    vi.useFakeTimers()
    const refetch = vi.fn()
    mockedUseMeetingShow.mockReturnValue(hookValue({ meeting: meeting({ has_transcript: false }), refetch }))
    render(<MeetingShow meetingId="m1" back={BACK} />)

    vi.advanceTimersByTime(9000)
    expect(refetch).not.toHaveBeenCalled()
    vi.useRealTimers()
  })
})
