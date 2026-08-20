import { fireEvent, render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { UpcomingMeetingRow } from "~/react/features/meetingsUpcomingIndex/components/UpcomingMeetingRow"

import { makeMeeting } from "../../../shared/meetingsFixtures"

function renderRow(meeting = makeMeeting(), highlight = false) {
  return render(<UpcomingMeetingRow meeting={meeting} highlight={highlight} timezone="UTC" />)
}

describe("UpcomingMeetingRow", () => {
  it("strikes through completed OR declined meetings (parity with the legacy row)", () => {
    const { getByText: getCompleted } = renderRow(makeMeeting({ title: "Done", is_completed: true }))
    expect(getCompleted("Done").className).toContain("line-through")

    // The legacy row struck through declined meetings too; they must stay in the
    // list (struck-through), not vanish.
    const { getByText: getDeclined } = renderRow(makeMeeting({ title: "Declined", is_declined: true }))
    expect(getDeclined("Declined").className).toContain("line-through")

    const { getByText: getActive } = renderRow(makeMeeting({ title: "Active" }))
    expect(getActive("Active").className).not.toContain("line-through")
  })

  it("reads the server-computed has_agenda flag, not the (blanked) list agenda string", () => {
    // List rows ship agenda="" to skip the per-row Y-doc fetch, so the indicator
    // must read has_agenda — a meeting with a collaborative-only agenda still
    // shows "Agenda set".
    const { getByText } = renderRow(makeMeeting({ agenda: "", has_agenda: true }))
    expect(getByText("Agenda set")).toBeTruthy()

    const { getByText: getNoAgenda } = renderRow(makeMeeting({ has_agenda: false }))
    expect(getNoAgenda("No agenda")).toBeTruthy()
  })

  it("pluralizes the attendee count", () => {
    const one = makeMeeting({ unresolved_attendees: [{ display_name: "A", status: null }] })
    expect(renderRow(one).getByText("1 attendee")).toBeTruthy()

    const two = makeMeeting({
      unresolved_attendees: [
        { display_name: "A", status: null },
        { display_name: "B", status: null },
      ],
    })
    expect(renderRow(two).getByText("2 attendees")).toBeTruthy()
  })

  describe("join button", () => {
    afterEach(() => {
      vi.restoreAllMocks()
    })

    it("opens the conferencing URL in a new tab when one is set", () => {
      const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
      const { getByRole } = renderRow(makeMeeting({ conferencing_url: "https://meet.example.com/abc" }))

      fireEvent.click(getByRole("button", { name: "Join" }))

      expect(openSpy).toHaveBeenCalledWith("https://meet.example.com/abc", "_blank", "noopener,noreferrer")
    })

    it("does not render when there is no conferencing URL", () => {
      const { queryByRole } = renderRow(makeMeeting({ conferencing_url: null }))
      expect(queryByRole("button", { name: "Join" })).toBeNull()
    })

    it("does not trigger the row's navigation to source_url", () => {
      const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
      const meeting = makeMeeting({
        conferencing_url: "https://meet.example.com/abc",
        source_url: "https://app.example.com/meetings/1",
      })
      const { getByRole, container } = renderRow(meeting)

      const joinButton = getByRole("button", { name: "Join" })
      const rowAnchor = container.querySelector('a[href="https://app.example.com/meetings/1"]')

      // jsdom has no htmx, so we can't exercise the real hx-boost regression (a Join
      // click reaching the boost handler via a boosted <a> ancestor). Asserting the
      // button is not a descendant of the row anchor pins the structural fix instead.
      expect(rowAnchor).not.toBeNull()
      expect(rowAnchor!.contains(joinButton)).toBe(false)

      // Behavioral: the click opens the conferencing URL in a new tab and is
      // prevented/non-propagated (defense in depth).
      const clickEvent = new MouseEvent("click", { bubbles: true, cancelable: true })
      fireEvent(joinButton, clickEvent)

      expect(clickEvent.defaultPrevented).toBe(true)
      expect(openSpy).toHaveBeenCalledWith("https://meet.example.com/abc", "_blank", "noopener,noreferrer")
    })
  })
})
