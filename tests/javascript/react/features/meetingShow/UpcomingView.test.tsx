import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

// Isolate UpcomingView's own gating logic by stubbing the heavy children
// (network, channels, Yjs/Prosemirror, video) and data hooks down to markers.
vi.mock("~/react/features/meetingShow/components/Header", () => ({ Header: () => <div>header</div> }))
vi.mock("~/react/features/meetingShow/components/MeetingTitle", () => ({ MeetingTitle: () => <div>meeting-title</div> }))
vi.mock("~/react/features/meetingShow/components/AgendaEditor", () => ({ AgendaEditor: () => <div>agenda-editor</div> }))
vi.mock("~/react/features/meetingShow/components/AttendeeList", () => ({
  AttendeeList: () => <div data-testid="attendee-list" />,
}))
vi.mock("~/react/features/meetingShow/components/CalendarMismatchBanner", () => ({
  CalendarMismatchBanner: () => <div data-testid="calendar-mismatch-banner" />,
}))
vi.mock("~/react/features/meetingShow/components/RecordingControls", () => ({
  RecordingControls: () => <div data-testid="recording-controls" />,
}))
vi.mock("~/react/shared/hooks/useCalendarConnection", () => ({
  useCalendarConnection: () => ({ calendar: { is_google_authenticated: true } }),
}))
vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ user: { id: "u1", display_name: "Test User" }, error: null }),
}))

import { UpcomingView } from "~/react/features/meetingShow/UpcomingView"
import type { MeetingBotState, MeetingDetail } from "~/react/features/meetingShow/types"

const BACK = { url: "/meetings", label: "Back to meetings" }

function makeMeeting(overrides: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    id: "m1",
    title: "Standup",
    summary: null,
    agenda: null,
    scheduled_at: null,
    scheduled_end_at: null,
    is_completed: false,
    is_upcoming: true,
    is_happening_now: false,
    is_recurring: false,
    is_initial_processing: false,
    is_deleted: false,
    did_recording_fail: false,
    has_transcript: false,
    has_chat_messages: false,
    workspace_id: "w1",
    sharing: "workspace",
    recording_id: null,
    conferencing_url: "https://zoom.us/j/123",
    user_attendees: [],
    unresolved_attendees: [],
    collection: null,
    previous_meeting_id: null,
    next_meeting_id: null,
    next_meeting_scheduled_at: null,
    ...overrides,
  }
}

function makeBot(overrides: Partial<MeetingBotState> = {}): MeetingBotState {
  return {
    bot_id: "b1",
    bot_status: "scheduled",
    bot_sub_status: null,
    is_processing_transcript: false,
    is_recording_in_progress: false,
    is_failed: false,
    will_record: false,
    is_schedulable: true,
    is_supported_meeting_platform: true,
    has_calendar_event: true,
    status_display: "Scheduled",
    failure_reason: null,
    ...overrides,
  }
}

describe("UpcomingView join link", () => {
  it("shows the join link before the meeting starts", () => {
    render(
      <UpcomingView
        meeting={makeMeeting({ is_happening_now: false, conferencing_url: "https://zoom.us/j/123" })}
        bot={makeBot({ will_record: false })}
        back={BACK}
        onLocalUpdate={vi.fn()}
        onServerUpdate={vi.fn()}
        onBotUpdate={vi.fn()}
      />
    )

    const link = screen.getByText("Click here to join.")
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute("href", "https://zoom.us/j/123")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
    expect(screen.getByTestId("recording-controls")).toBeInTheDocument()
    expect(screen.getByTestId("attendee-list")).toBeInTheDocument()
  })

  it("still shows the join link while the meeting is in progress", () => {
    render(
      <UpcomingView
        meeting={makeMeeting({ is_happening_now: true, conferencing_url: "https://zoom.us/j/123" })}
        bot={makeBot({ will_record: true, has_calendar_event: false })}
        back={BACK}
        onLocalUpdate={vi.fn()}
        onServerUpdate={vi.fn()}
        onBotUpdate={vi.fn()}
      />
    )

    const link = screen.getByText("Click here to join.")
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute("href", "https://zoom.us/j/123")
    expect(screen.queryByTestId("recording-controls")).toBeNull()
    expect(screen.queryByTestId("attendee-list")).toBeNull()
    expect(screen.queryByTestId("calendar-mismatch-banner")).toBeNull()
  })

  it("shows no join link when there is no conferencing URL", () => {
    render(
      <UpcomingView
        meeting={makeMeeting({ is_happening_now: false, conferencing_url: null })}
        bot={makeBot()}
        back={BACK}
        onLocalUpdate={vi.fn()}
        onServerUpdate={vi.fn()}
        onBotUpdate={vi.fn()}
      />
    )

    expect(screen.queryByText("Click here to join.")).toBeNull()
  })
})
