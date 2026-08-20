import { afterEach, describe, expect, test, vi } from "vitest"

import { DecisionMarker } from "~/react/composites/DecisionMarker"
import type { Decision, User } from "~/react/shared/types"

import { cleanup, fireEvent, render, screen } from "../shared/testUtils"

// A cold cache (no seeded user) makes useCurrentUser fetch; keep it pending so
// the "still loading" test observes the unresolved state without a real request.
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: () => new Promise(() => {}) }))

import { resetCurrentUser, setCurrentUser } from "../shared/currentUserFixtures"

const decider: User = { id: "u1", display_name: "Alice", picture: null }

afterEach(() => {
  cleanup()
  resetCurrentUser()
})

function decision(decidedBy: User | null): Decision {
  return {
    id: "d1",
    comment_gid: "gid://convictional/EmailThreadComment/c1",
    comment_preview: "Ship it",
    decided_by: decidedBy,
    decided_at: "2026-06-01T00:00:00Z",
  }
}

describe("DecisionMarker", () => {
  test("undecided renders a quiet Decide button that toggles", () => {
    const onToggle = vi.fn()
    render(<DecisionMarker decision={undefined} onToggle={onToggle} />)

    const button = screen.getByRole("button", { name: /Decide/ })
    expect(screen.queryByText("Decision")).not.toBeInTheDocument()
    fireEvent.click(button)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  test("the decider can clear their own decision", () => {
    setCurrentUser({ id: "u1" })
    const onToggle = vi.fn()
    render(<DecisionMarker decision={decision(decider)} onToggle={onToggle} />)

    expect(screen.getByText("Decision")).toBeInTheDocument()
    // Avatar placeholder uses the first initial when there's no picture.
    expect(screen.getByTitle("Alice")).toBeInTheDocument()
    // The decider sees first-person attribution on the button's accessible name.
    fireEvent.click(screen.getByRole("button", { name: /you decided at .* undo this decision/i }))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  test("an admin can clear someone else's decision", () => {
    setCurrentUser({ id: "someone-else", is_admin: true })
    const onToggle = vi.fn()
    render(<DecisionMarker decision={decision(decider)} onToggle={onToggle} />)

    fireEvent.click(screen.getByRole("button", { name: /undo this decision/i }))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  test("a non-decider, non-admin sees a static badge, not a button", () => {
    setCurrentUser({ id: "someone-else" })
    const onToggle = vi.fn()
    render(<DecisionMarker decision={decision(decider)} onToggle={onToggle} />)

    expect(screen.getByText("Decision")).toBeInTheDocument()
    // Rendered as a non-interactive badge: no button to focus/activate.
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    fireEvent.click(screen.getByText("Decision"))
    expect(onToggle).not.toHaveBeenCalled()
  })

  test("stays non-interactive while the current user is still loading", () => {
    // The viewer is the decider, but the fetch hasn't resolved (cold cache, no
    // seeded user) — don't render a clickable button yet, nor the inert state.
    const onToggle = vi.fn()
    render(<DecisionMarker decision={decision(decider)} onToggle={onToggle} />)

    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    fireEvent.click(screen.getByText("Decision"))
    expect(onToggle).not.toHaveBeenCalled()
  })

  test("decided without a decider omits the avatar", () => {
    setCurrentUser({ id: "u1", is_admin: true })
    render(<DecisionMarker decision={decision(null)} onToggle={vi.fn()} />)

    expect(screen.getByText("Decision")).toBeInTheDocument()
    expect(screen.queryByTitle("Alice")).not.toBeInTheDocument()
  })
})
