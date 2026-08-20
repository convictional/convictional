import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

import { WhatsNewPanel } from "~/react/features/postShow/components/WhatsNewPanel"
import type { WhatsNew } from "~/react/features/postShow/whatsNew"

import { buildComment, buildUser } from "./fixtures"

function buildWhatsNew(overrides: Partial<WhatsNew> = {}): WhatsNew {
  return {
    totalCount: 2,
    lastVisitAt: "2026-05-10T00:00:00Z",
    decisions: [],
    firstNewCommentId: "c1",
    groups: [
      {
        parentCommentId: null,
        contextAuthorName: null,
        comments: [
          { id: "c1", user: buildUser({ display_name: "Bob" }), preview: "first new" },
          { id: "c2", user: buildUser({ display_name: "Cara" }), preview: "second new" },
        ],
      },
    ],
    ...overrides,
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  apiFetchMock.mockReset()
  apiFetchMock.mockReturnValue(new Promise(() => {}))
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("WhatsNewPanel", () => {
  test("hovering a What's New avatar opens the profile card", async () => {
    const whatsNew = buildWhatsNew({
      totalCount: 1,
      decisions: [],
      groups: [
        {
          parentCommentId: null,
          contextAuthorName: null,
          comments: [{ id: "c1", user: buildUser({ id: "wn-user", display_name: "Bob" }), preview: "first new" }],
        },
      ],
    })
    const { container } = render(<WhatsNewPanel whatsNew={whatsNew} onJump={vi.fn()} onDismiss={vi.fn()} />)

    const avatar = container.querySelector(".avatar")!
    fireEvent.mouseEnter(avatar.parentElement!)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledWith("/api/people/wn-user")
    expect(apiFetchMock).toHaveBeenCalledWith("/api/users/wn-user/top_goal?expand=parent")
  })

  test("renders the count and the grouped rows", () => {
    render(<WhatsNewPanel whatsNew={buildWhatsNew()} onJump={vi.fn()} onDismiss={vi.fn()} />)
    expect(screen.getByText(/2 new since/)).toBeInTheDocument()
    expect(screen.getByText("first new")).toBeInTheDocument()
    expect(screen.getByText("second new")).toBeInTheDocument()
  })

  test("renders a row for each new decision with the marker name", () => {
    const decisions = [
      { comment: buildComment({ id: "d1", user: buildUser({ display_name: "Alice" }) }), decidedByName: "Dee" },
      { comment: buildComment({ id: "d2", user: buildUser({ display_name: "Bea" }) }), decidedByName: null },
    ]
    render(<WhatsNewPanel whatsNew={buildWhatsNew({ totalCount: 2, groups: [], decisions })} onJump={vi.fn()} onDismiss={vi.fn()} />)
    expect(screen.getAllByText("Decision")).toHaveLength(2)
    expect(screen.getByText("Alice")).toBeInTheDocument()
    expect(screen.getByText("Bea")).toBeInTheDocument()
    expect(screen.getByText("marked by Dee")).toBeInTheDocument()
  })

  test("clicking a row jumps to that comment", () => {
    const onJump = vi.fn()
    render(<WhatsNewPanel whatsNew={buildWhatsNew()} onJump={onJump} onDismiss={vi.fn()} />)
    fireEvent.click(screen.getByText("first new"))
    expect(onJump).toHaveBeenCalledWith("c1")
  })

  test("Jump to first new targets the first new comment", () => {
    const onJump = vi.fn()
    render(<WhatsNewPanel whatsNew={buildWhatsNew()} onJump={onJump} onDismiss={vi.fn()} />)
    fireEvent.click(screen.getByText("Jump to first new"))
    expect(onJump).toHaveBeenCalledWith("c1")
  })

  test("Dismiss invokes onDismiss", () => {
    const onDismiss = vi.fn()
    render(<WhatsNewPanel whatsNew={buildWhatsNew()} onJump={vi.fn()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByText("Dismiss"))
    expect(onDismiss).toHaveBeenCalled()
  })
})
