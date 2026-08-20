import { cleanup, fireEvent, render, screen } from "../../shared/testUtils"
import { afterEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/features/postShow/components/ReplyComposer", () => ({
  ReplyComposer: () => <div data-testid="reply-composer" />,
}))

import { CommentActions } from "~/react/features/postShow/components/CommentActions"

import { resetCurrentUser, setCurrentUser } from "../../shared/currentUserFixtures"
import { buildComment } from "./fixtures"

function decision() {
  return {
    id: "d1",
    comment_gid: "gid://convictional/PostComment/c1",
    comment_preview: "Decided",
    decided_by: { id: "u1", display_name: "Alice", picture: null },
    decided_at: "2026-06-01T00:00:00Z",
  }
}

function renderActions(props: Partial<Parameters<typeof CommentActions>[0]> = {}) {
  return render(
    <CommentActions
      comment={buildComment({ id: "c1" })}
      workspaceId="ws-1"
      currentUserId="viewer"
      decision={undefined}
      onReply={vi.fn().mockResolvedValue(buildComment())}
      onToggleReaction={vi.fn()}
      onToggleDecision={vi.fn()}
      {...props}
    />
  )
}

afterEach(() => {
  cleanup()
  resetCurrentUser()
})

describe("CommentActions", () => {
  test("Reply expands the inline composer", () => {
    renderActions()
    expect(screen.queryByTestId("reply-composer")).not.toBeInTheDocument()
    fireEvent.click(screen.getByText("Reply"))
    expect(screen.getByTestId("reply-composer")).toBeInTheDocument()
  })

  test("shows the Decide affordance and toggles when undecided", () => {
    const onToggleDecision = vi.fn()
    renderActions({ decision: undefined, onToggleDecision })
    expect(screen.queryByText("Decision")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Decide/ }))
    expect(onToggleDecision).toHaveBeenCalledTimes(1)
  })

  test("shows the decision pill and toggles when decided", () => {
    // The marker reads the current user from the store to gate undeciding; the
    // viewer here is the decider ("u1"), so the pill stays clickable.
    setCurrentUser({ id: "u1", display_name: "Alice" })
    const onToggleDecision = vi.fn()
    renderActions({ decision: decision(), onToggleDecision })
    expect(screen.getByText("Decision")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /undo this decision/i }))
    expect(onToggleDecision).toHaveBeenCalledTimes(1)
  })
})
