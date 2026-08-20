import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import { ActivityEvent } from "~/react/features/emailThreadShow/components/ActivityEvent"
import type { EmailThreadEvent } from "~/react/shared/types"

afterEach(() => cleanup())

function makeEvent(overrides: Partial<EmailThreadEvent> = {}): EmailThreadEvent {
  return {
    id: "evt-1",
    action: "assigned",
    created_at: "2026-01-01T00:00:00Z",
    creator: { id: "user-1", display_name: "Alice", picture: null },
    details: { type: "assigned", subject_label: "Bob" },
    ...overrides,
  }
}

describe("ActivityEvent", () => {
  it("renders assignment events", () => {
    const { rerender } = render(<ActivityEvent event={makeEvent()} />)
    expect(screen.getByText("Alice assigned to Bob")).toBeInTheDocument()

    rerender(
      <ActivityEvent
        event={makeEvent({ action: "unassigned", details: { type: "unassigned", subject_label: "Bob" } })}
      />
    )
    expect(screen.getByText("Alice unassigned Bob")).toBeInTheDocument()

    // Falls back to "someone" (no trailing space) when the subject is unknown.
    rerender(
      <ActivityEvent event={makeEvent({ action: "assigned", details: { type: "assigned", subject_label: null } })} />
    )
    expect(screen.getByText("Alice assigned to someone")).toBeInTheDocument()
  })

  it("renders collaborator events with and without a reason", () => {
    const { rerender } = render(
      <ActivityEvent
        event={makeEvent({
          action: "added_collaborator",
          details: { type: "added_collaborator", subject_label: "Bob", reason: "to review." },
        })}
      />
    )
    expect(screen.getByText("Alice invited Bob to review.")).toBeInTheDocument()

    rerender(
      <ActivityEvent
        event={makeEvent({
          action: "added_collaborator",
          details: { type: "added_collaborator", subject_label: null, reason: null },
        })}
      />
    )
    expect(screen.getByText("Alice invited a collaborator to collaborate.")).toBeInTheDocument()
  })

  it("falls back to 'Someone' when the creator is missing", () => {
    render(<ActivityEvent event={makeEvent({ creator: null })} />)
    expect(screen.getByText("Someone assigned to Bob")).toBeInTheDocument()
  })

  it("renders the event id and a timestamp, and nothing for an unknown action", () => {
    const { container, rerender } = render(<ActivityEvent event={makeEvent()} />)
    expect(container.querySelector("[data-event-id='evt-1']")).toBeInTheDocument()
    expect(container.querySelector("time")).toBeInTheDocument()

    rerender(<ActivityEvent event={makeEvent({ action: "mystery", details: null })} />)
    expect(container.innerHTML).toBe("")
  })
})
