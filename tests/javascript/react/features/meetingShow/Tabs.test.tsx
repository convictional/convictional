import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// Stub the panels so these tests exercise only the tab-selection logic, not the
// summary editor / markdown rendering that the panels pull in.
vi.mock("~/react/features/meetingShow/components/SummaryTab", () => ({
  SummaryTab: () => <div>summary-panel</div>,
}))
vi.mock("~/react/features/meetingShow/components/AgendaEditor", () => ({
  AgendaEditor: () => <div data-testid="agenda-editor" />,
}))

import { Tabs } from "~/react/features/meetingShow/components/Tabs"
import type { MeetingDetail } from "~/react/features/meetingShow/types"

function meeting(overrides: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    id: "m1",
    title: "Standup",
    summary: null,
    agenda: "Agenda body",
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

function renderTabs(m: MeetingDetail) {
  return render(<Tabs meeting={m} onLocalUpdate={vi.fn()} onServerUpdate={vi.fn()} />)
}

function activeTabLabel() {
  return screen
    .getAllByRole("tab")
    .find(tab => tab.getAttribute("aria-selected") === "true")
    ?.textContent?.trim()
}

beforeEach(() => {
  window.location.hash = ""
})

afterEach(() => {
  cleanup()
  window.location.hash = ""
})

describe("Tabs", () => {
  test("defaults to Summary when a summary is present", () => {
    renderTabs(meeting({ summary: "All done" }))
    expect(activeTabLabel()).toBe("Summary")
    expect(screen.getByText("summary-panel")).toBeInTheDocument()
  })

  test("defaults to Agenda and disables Summary when there is no summary", () => {
    renderTabs(meeting({ summary: null }))
    expect(activeTabLabel()).toBe("Agenda")
    expect(screen.getByTestId("agenda-editor")).toBeInTheDocument()
    expect(screen.queryByText("No agenda content available for this completed meeting.")).toBeNull()
    // The Summary tab renders disabled (no aria-selected handle to activate).
    expect(document.querySelector('[role="tab"][aria-disabled="true"]')).not.toBeNull()
  })

  test("honours a #summary hash on mount when a summary exists", () => {
    window.location.hash = "#summary"
    renderTabs(meeting({ summary: "All done" }))
    expect(activeTabLabel()).toBe("Summary")
  })

  test("ignores a #summary hash when no summary is available", () => {
    window.location.hash = "#summary"
    renderTabs(meeting({ summary: null }))
    expect(activeTabLabel()).toBe("Agenda")
  })

  test("clicking a tab activates it and updates the hash", () => {
    renderTabs(meeting({ summary: "All done" }))
    fireEvent.click(screen.getByRole("tab", { name: "Agenda" }))
    expect(activeTabLabel()).toBe("Agenda")
    expect(window.location.hash).toBe("#agenda")
    expect(screen.getByTestId("agenda-editor")).toBeInTheDocument()
  })
})
