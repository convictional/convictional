import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { MeetingAttendees } from "~/react/composites/meetings/MeetingAttendees"
import type { User } from "~/react/shared/types"

function makeUser(overrides: Partial<User> = {}): User {
  return { id: "user-1", display_name: "Alice", picture: null, ...overrides }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("MeetingAttendees", () => {
  it("renders nothing when there are no attendees", () => {
    const { container } = render(<MeetingAttendees resolved={[]} unresolved={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it("shows the combined total of resolved and unresolved attendees", () => {
    render(
      <MeetingAttendees
        resolved={[makeUser(), makeUser({ id: "user-2", display_name: "Bob" })]}
        unresolved={[{ display_name: "Guest", status: null }]}
      />
    )
    expect(screen.getByText("3")).toBeTruthy()
  })

  it("lists names in the hover tooltip, with ? for nameless unresolved attendees", async () => {
    const { container } = render(
      <MeetingAttendees resolved={[makeUser()]} unresolved={[{ display_name: null, status: null }]} />
    )

    fireEvent.mouseEnter(container.querySelector("span")!)
    await act(async () => {
      vi.advanceTimersByTime(500)
    })

    expect(screen.getByText("Alice, ?")).toBeTruthy()
  })
})
