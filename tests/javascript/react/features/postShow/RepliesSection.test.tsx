import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

vi.mock("~/react/features/postShow/components/ReplyComposer", () => ({
  ReplyComposer: () => <div data-testid="reply-composer" />,
}))

import { RepliesSection } from "~/react/features/postShow/components/RepliesSection"
import type { CommentThreadProps } from "~/react/features/postShow/commentThread"

import { buildComment, buildUser } from "./fixtures"

function buildCtx(): CommentThreadProps {
  return {
    workspaceId: "ws-1",
    currentUserId: "viewer",
    decisionCommentId: null,
    postIsDecided: false,
    canDecide: false,
    newCommentIds: new Set(),
    registerRef: () => () => {},
    highlightedId: null,
    createComment: vi.fn().mockResolvedValue(null),
    editComment: vi.fn().mockResolvedValue(null),
    deleteComment: vi.fn().mockResolvedValue(undefined),
    toggleReaction: vi.fn(),
    setDecision: vi.fn(),
  }
}

function buildParent() {
  return buildComment({
    id: "p1",
    replies: [
      buildComment({ id: "r1", parent_id: "p1", user: buildUser({ id: "u1", display_name: "Bob" }) }),
      buildComment({ id: "r2", parent_id: "p1", user: buildUser({ id: "u2", display_name: "Cara" }) }),
    ],
  })
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

describe("RepliesSection", () => {
  const renderReply = (reply: { id: string }) => <div data-testid={`reply-${reply.id}`}>{reply.id}</div>

  test("hovering a collapsed reply-author avatar opens the profile card", async () => {
    const { container } = render(
      <RepliesSection comment={buildParent()} ctx={buildCtx()} renderReply={renderReply} />
    )
    fireEvent.click(screen.getByText("Hide 2 replies"))

    // Stack layout renders the UserHoverCard trigger <span> directly under .avatar-group.
    const trigger = container.querySelector(".avatar-group > span")!
    fireEvent.mouseEnter(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledWith("/api/people/u1")
    expect(apiFetchMock).toHaveBeenCalledWith("/api/users/u1/top_goal?expand=parent")
  })

  test("renders nothing when there are no replies", () => {
    const { container } = render(
      <RepliesSection comment={buildComment({ replies: [] })} ctx={buildCtx()} renderReply={renderReply} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  test("expanded by default; collapse shows the show-replies button", () => {
    render(<RepliesSection comment={buildParent()} ctx={buildCtx()} renderReply={renderReply} />)
    expect(screen.getByText("Hide 2 replies")).toBeInTheDocument()
    expect(screen.getByTestId("reply-r1")).toBeInTheDocument()
    fireEvent.click(screen.getByText("Hide 2 replies"))
    expect(screen.getByText("Show 2 replies")).toBeInTheDocument()
  })

  test("Add a reply reveals the inline composer", () => {
    render(<RepliesSection comment={buildParent()} ctx={buildCtx()} renderReply={renderReply} />)
    expect(screen.queryByTestId("reply-composer")).not.toBeInTheDocument()
    fireEvent.click(screen.getByText("Add a reply"))
    expect(screen.getByTestId("reply-composer")).toBeInTheDocument()
  })
})
