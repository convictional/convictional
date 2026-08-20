import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MeetingCard } from "~/react/composites/meetings/MeetingCard"

import { makeMeeting } from "../../shared/meetingsFixtures"

function renderCard(meeting = makeMeeting()) {
  return render(<MeetingCard meeting={meeting} onMeetingUpdated={vi.fn()} timezone="UTC" />)
}

describe("MeetingCard", () => {
  it("links the title to the meeting and falls back for untitled meetings", () => {
    renderCard(makeMeeting({ title: "Weekly sync", source_url: "/meetings/meeting-1" }))
    const title = screen.getByText("Weekly sync")
    expect(title.closest("a")?.getAttribute("href")).toBe("/meetings/meeting-1")

    renderCard(makeMeeting({ id: "meeting-2", title: "" }))
    expect(screen.getByText("Untitled meeting")).toBeTruthy()
  })

  it("shows the recurring indicator only for recurring meetings", () => {
    const { container } = renderCard(makeMeeting({ is_recurring: true }))
    expect(container.textContent).toContain("event_repeat")

    const { container: oneOff } = renderCard(makeMeeting({ id: "meeting-2" }))
    expect(oneOff.textContent).not.toContain("event_repeat")
  })

  it("shows the grouped attendee count across resolved and unresolved attendees", () => {
    renderCard(
      makeMeeting({
        user_attendees: [{ id: "u1", display_name: "Alice", picture: null }],
        unresolved_attendees: [{ display_name: "Guest", status: null }],
      })
    )
    expect(screen.getByText("2")).toBeTruthy()
  })
})
