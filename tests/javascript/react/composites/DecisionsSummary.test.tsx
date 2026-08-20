import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { DecisionsSummary } from "~/react/composites/DecisionsSummary"
import type { Decision } from "~/react/shared/types"

afterEach(cleanup)

function buildDecision(overrides: Partial<Decision> = {}): Decision {
  return {
    id: "d1",
    comment_gid: "gid://convictional/PostComment/c1",
    comment_preview: "We ship on Friday",
    decided_by: { id: "u1", display_name: "Alice", picture: null },
    decided_at: "2026-06-01T00:00:00Z",
    ...overrides,
  }
}

describe("DecisionsSummary", () => {
  test("renders nothing when there are no decisions", () => {
    const { container } = render(<DecisionsSummary decisions={[]} onJump={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  test("renders a row per decision and jumps by comment_gid", () => {
    const onJump = vi.fn()
    render(
      <DecisionsSummary
        decisions={[buildDecision(), buildDecision({ id: "d2", comment_gid: "gid://convictional/PostComment/c2" })]}
        onJump={onJump}
      />
    )

    expect(screen.getByText("2 decisions")).toBeInTheDocument()
    expect(screen.getAllByText("We ship on Friday")).toHaveLength(2)
    fireEvent.click(screen.getAllByText("We ship on Friday")[0])
    expect(onJump).toHaveBeenCalledWith("gid://convictional/PostComment/c1")
  })

  test("shows a tombstone for a deleted anchor comment", () => {
    render(<DecisionsSummary decisions={[buildDecision({ comment_preview: null })]} onJump={vi.fn()} />)
    expect(screen.getByText("This comment was deleted")).toBeInTheDocument()
    expect(screen.getByText("Decision")).toBeInTheDocument()
  })
})
