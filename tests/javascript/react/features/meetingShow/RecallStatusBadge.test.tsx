import { render, screen } from "@testing-library/react"
import { describe, expect, test } from "vitest"

import { RecallStatusBadge } from "~/react/features/meetingShow/components/RecallStatusBadge"
import type { MeetingBotState } from "~/react/features/meetingShow/types"

function botState(overrides: Partial<MeetingBotState> = {}): MeetingBotState {
  return {
    bot_id: "b1",
    bot_status: "joining",
    bot_sub_status: null,
    is_processing_transcript: false,
    is_recording_in_progress: false,
    is_failed: false,
    will_record: true,
    is_schedulable: true,
    is_supported_meeting_platform: true,
    has_calendar_event: true,
    status_display: "Joining meeting…",
    failure_reason: null,
    ...overrides,
  }
}

describe("RecallStatusBadge", () => {
  test("renders nothing when the server has no status to display", () => {
    const { container } = render(<RecallStatusBadge bot={botState({ status_display: "" })} />)
    expect(container).toBeEmptyDOMElement()
  })

  test("renders a failure as plain muted text without an icon (the shell shows videocam_off)", () => {
    const { container } = render(
      <RecallStatusBadge
        bot={botState({
          is_failed: true,
          status_display: "Recording failed",
          failure_reason: "Bot was removed from the call",
        })}
      />
    )

    expect(screen.getByText("Recording failed")).toBeInTheDocument()
    expect(screen.getByText("Bot was removed from the call")).toBeInTheDocument()
    // No icon and no coloured box — the page shell owns the videocam_off heading.
    expect(screen.queryByText("videocam_off")).not.toBeInTheDocument()
    expect(container.querySelector(".border")).toBeNull()
  })

  test("shows a red box (no spinner) when the meeting is unschedulable", () => {
    const { container } = render(
      <RecallStatusBadge bot={botState({ bot_status: "unschedulable", status_display: "Cannot be recorded" })} />
    )

    expect(screen.getByText("Cannot be recorded")).toBeInTheDocument()
    expect(container.querySelector(".border-red-700")).not.toBeNull()
    expect(container.querySelector(".loading-spinner")).toBeNull()
  })

  test("does not repeat the failure reason when it duplicates the status display", () => {
    render(
      <RecallStatusBadge
        bot={botState({ is_failed: true, status_display: "Recording failed", failure_reason: "Recording failed" })}
      />
    )

    expect(screen.getAllByText("Recording failed")).toHaveLength(1)
  })

  test("shows the recording-in-progress icon", () => {
    render(<RecallStatusBadge bot={botState({ is_recording_in_progress: true, status_display: "Recording" })} />)
    expect(screen.getByText("fiber_manual_record")).toBeInTheDocument()
  })

  test("shows the schedule icon when scheduled", () => {
    render(<RecallStatusBadge bot={botState({ bot_status: "scheduled", status_display: "Scheduled" })} />)
    expect(screen.getByText("schedule")).toBeInTheDocument()
  })

  test("shows a spinner (no icon) while processing the transcript", () => {
    const { container } = render(
      <RecallStatusBadge bot={botState({ is_processing_transcript: true, status_display: "Processing" })} />
    )
    expect(container.querySelector(".loading-spinner")).not.toBeNull()
  })

  test("frames a terminal 'cannot be recorded' message without a spinner", () => {
    // No bot dispatched (status NONE) and not going to record: a terminal
    // limitation, not work in progress.
    const { container } = render(
      <RecallStatusBadge
        bot={botState({
          bot_status: "",
          will_record: false,
          is_schedulable: false,
          status_display: "This meeting cannot be recorded because it is scheduled to start within 20 minutes.",
        })}
      />
    )

    expect(screen.getByText(/cannot be recorded/i)).toBeInTheDocument()
    expect(container.querySelector(".loading-spinner")).toBeNull()
  })

  test("frames a 'will be recorded' message as a scheduled box without a spinner", () => {
    const { container } = render(
      <RecallStatusBadge
        bot={botState({ bot_status: "", will_record: true, status_display: "This meeting will be recorded." })}
      />
    )

    expect(screen.getByText("schedule")).toBeInTheDocument()
    expect(container.querySelector(".loading-spinner")).toBeNull()
  })

  test("falls back to the processing spinner for any other in-progress state", () => {
    // No failure / recording / scheduled / processing flag set: the fallthrough
    // branch still renders a spinner rather than crashing or rendering blank.
    const { container } = render(<RecallStatusBadge bot={botState({ status_display: "Joining meeting…" })} />)
    expect(container.querySelector(".loading-spinner")).not.toBeNull()
  })
})
