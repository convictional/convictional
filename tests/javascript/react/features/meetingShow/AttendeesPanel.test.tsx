import { render, screen } from "@testing-library/react"
import { describe, expect, test } from "vitest"

import { AttendeesPanel } from "~/react/features/meetingShow/components/AttendeesPanel"
import type { AttendeeStatus, UserAttendee } from "~/react/features/meetingShow/types"

function user(overrides: Partial<UserAttendee> = {}): UserAttendee {
  return { id: crypto.randomUUID(), display_name: "Ada Lovelace", picture: null, ...overrides }
}

function unresolved(overrides: Partial<AttendeeStatus> = {}): AttendeeStatus {
  return { display_name: "guest@example.com", status: "accepted", ...overrides }
}

describe("AttendeesPanel", () => {
  test("renders nothing when there are no attendees", () => {
    const { container } = render(<AttendeesPanel resolved={[]} unresolved={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  test("renders a resolved attendee without a picture using display_name (no crash on the initial)", () => {
    // Regression: the panel previously read user.name (undefined), so Avatar's
    // displayName.charAt(0) threw for any pictureless resolved attendee.
    render(<AttendeesPanel resolved={[user({ display_name: "Ada Lovelace", picture: null })]} unresolved={[]} />)

    expect(screen.getByTitle("Ada Lovelace")).toBeInTheDocument()
    expect(screen.getByText("A")).toBeInTheDocument()
  })

  test("renders resolved and unresolved attendees together", () => {
    render(
      <AttendeesPanel
        resolved={[user({ display_name: "Grace Hopper", picture: null })]}
        unresolved={[unresolved({ display_name: "guest@example.com" })]}
      />
    )

    expect(screen.getByTitle("Grace Hopper")).toBeInTheDocument()
    expect(screen.getByTitle("guest@example.com")).toBeInTheDocument()
  })

  test("falls back to '?' for an unresolved attendee with no display name", () => {
    render(<AttendeesPanel resolved={[]} unresolved={[unresolved({ display_name: null })]} />)
    expect(screen.getByTitle("?")).toBeInTheDocument()
  })
})
