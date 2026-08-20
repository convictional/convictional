import { act, cleanup, fireEvent, render, screen } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

// The inline editor wraps ProseMirror; stub it so display-mode rendering tests
// stay fast and focused.
vi.mock("~/react/composites/comment/CommentEditor", () => ({
  CommentEditor: () => <div data-testid="edit-form" />,
}))

import { Comment } from "~/react/features/postShow/components/Comment"
import type { CommentThreadProps } from "~/react/features/postShow/commentThread"

import { buildComment, buildUser } from "./fixtures"

function buildCtx(overrides: Partial<CommentThreadProps> = {}): CommentThreadProps {
  return {
    workspaceId: "ws-1",
    currentUserId: "viewer",
    decisionsByGid: new Map(),
    toggleDecision: vi.fn(),
    newCommentIds: new Set(),
    registerRef: () => () => {},
    highlightedId: null,
    createComment: vi.fn().mockResolvedValue(null),
    editComment: vi.fn().mockResolvedValue(null),
    deleteComment: vi.fn().mockResolvedValue(undefined),
    toggleReaction: vi.fn(),
    ...overrides,
  }
}

function decision(commentGid: string) {
  return {
    id: "d1",
    comment_gid: commentGid,
    comment_preview: "Decided",
    decided_by: { id: "u1", display_name: "Alice", picture: null },
    decided_at: "2026-06-01T00:00:00Z",
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

describe("Comment", () => {
  test("hovering the comment author avatar opens the profile card", async () => {
    render(<Comment comment={buildComment({ user: buildUser({ id: "cmt-user" }) })} ctx={buildCtx()} />)

    const avatar = document.querySelector(".avatar")!
    fireEvent.mouseEnter(avatar.parentElement!)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledWith("/api/people/cmt-user")
    expect(apiFetchMock).toHaveBeenCalledWith("/api/users/cmt-user/top_goal?expand=parent")
  })

  test("renders author name and content", () => {
    render(<Comment comment={buildComment({ content: "Hello there" })} ctx={buildCtx()} />)
    expect(screen.getByText("Alice")).toBeInTheDocument()
    expect(screen.getByText("Hello there")).toBeInTheDocument()
  })

  test("shows the decision marker when this comment is decided", () => {
    const comment = buildComment({ id: "comment-1", global_id: "gid://convictional/PostComment/comment-1" })
    const ctx = buildCtx({ decisionsByGid: new Map([[comment.global_id, decision(comment.global_id)]]) })
    render(<Comment comment={comment} ctx={ctx} />)
    expect(screen.getByText("Decision")).toBeInTheDocument()
  })

  test("clicking the marker toggles the decision via ctx", () => {
    const comment = buildComment({ id: "comment-1", global_id: "gid://convictional/PostComment/comment-1" })
    const toggleDecision = vi.fn()
    render(<Comment comment={comment} ctx={buildCtx({ toggleDecision })} />)
    fireEvent.click(screen.getByRole("button", { name: /Decide/ }))
    expect(toggleDecision).toHaveBeenCalledWith(comment.global_id)
  })

  test("shows the New badge for new comments", () => {
    const ctx = buildCtx({ newCommentIds: new Set(["comment-1"]) })
    render(<Comment comment={buildComment({ id: "comment-1" })} ctx={ctx} />)
    expect(screen.getByText("New")).toBeInTheDocument()
  })

  // The toggle is gated on measured overflow. The clamp uses `-webkit-line-clamp`,
  // which collapses the element's `scrollHeight` down to the clamped height, so the
  // true content height is only observable with the clamp neutralized (`display:
  // block`) — which is exactly how the component measures. jsdom has no layout, so
  // model that behavior: `scrollHeight` reports the natural (unclamped) height only
  // while `display` is "block", and the clamped height otherwise.
  function mockClampHeights(naturalHeight: number, clampedHeight = 80) {
    const scroll = vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(function (
      this: HTMLElement
    ) {
      return this.style.display === "block" ? naturalHeight : clampedHeight
    })
    const client = vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(clampedHeight)
    return () => {
      scroll.mockRestore()
      client.mockRestore()
    }
  }

  test("renders a show-more toggle when content overflows the clamp", () => {
    const restore = mockClampHeights(200, 80)
    render(<Comment comment={buildComment({ content: "x".repeat(401) })} ctx={buildCtx()} />)
    const toggle = screen.getByText("Show more")
    fireEvent.click(toggle)
    expect(screen.getByText("Show less")).toBeInTheDocument()
    restore()
  })

  test("shows no toggle when long content still fits within the clamp", () => {
    // Regression: a >400-char comment that fit within the 4-line clamp used to
    // render a Show more button that revealed nothing when clicked.
    const restore = mockClampHeights(80, 80)
    render(<Comment comment={buildComment({ content: "x".repeat(401) })} ctx={buildCtx()} />)
    expect(screen.queryByText("Show more")).not.toBeInTheDocument()
    restore()
  })

  test("re-measures on a late reflow (image/font load) and reveals the toggle", () => {
    // Regression: `-webkit-line-clamp` collapses the box's scrollHeight to the
    // clamped height while the content is a single block child (the markdown wrapper
    // is), so a naive `scrollHeight > clientHeight` read never detected overflow. On top
    // of that, content can fit at first paint then reflow taller as fonts/images settle,
    // which the ResizeObserver misses (the box height is pinned). The component reads the
    // natural height with the clamp neutralized and re-measures on a captured `load`.
    let naturalHeight = 80 // fits within the clamp at first paint
    const scroll = vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(function (
      this: HTMLElement
    ) {
      return this.style.display === "block" ? naturalHeight : 80
    })
    const client = vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(80)

    const { container } = render(<Comment comment={buildComment({ content: "x".repeat(401) })} ctx={buildCtx()} />)
    expect(screen.queryByText("Show more")).not.toBeInTheDocument()

    // An image inside the markdown finishes loading and reflows the text taller.
    naturalHeight = 200
    const content = container.querySelector(".line-clamp-4")!
    act(() => {
      content.dispatchEvent(new Event("load"))
    })

    expect(screen.getByText("Show more")).toBeInTheDocument()
    scroll.mockRestore()
    client.mockRestore()
  })

  test("renders a link preview when present", () => {
    const comment = buildComment({
      link_preview: { url: "https://example.com/page", title: "Example", description: null, image_url: null },
    })
    render(<Comment comment={comment} ctx={buildCtx()} />)
    expect(screen.getByText("Example")).toBeInTheDocument()
    expect(screen.getByText("example.com")).toBeInTheDocument()
  })

  test("a file attachment preview strips the duplicate inline link, leaving only the card", () => {
    const comment = buildComment({
      content: "[report.pdf](https://x/report.pdf)",
      link_preview: {
        url: "https://x/report.pdf",
        title: null,
        description: null,
        image_url: null,
        resource_kind: "file",
        file: null,
      },
    })
    const { container } = render(<Comment comment={comment} ctx={buildCtx()} />)
    const scope = container.querySelector("[data-comment-id]")!
    // Only the file card's download anchor survives; the inline [report.pdf] link is gone.
    const anchors = scope.querySelectorAll("a")
    expect(anchors.length).toBe(1)
    expect(anchors[0].getAttribute("href")).toBe("https://x/report.pdf")
    expect(scope.textContent).not.toContain("report.pdf")
  })

  test("a non-file preview keeps both the inline link and the card", () => {
    const comment = buildComment({
      content: "[the doc](https://x/doc)",
      link_preview: {
        url: "https://x/doc",
        title: null,
        description: null,
        image_url: null,
        resource_kind: "document",
        file: null,
      },
    })
    render(<Comment comment={comment} ctx={buildCtx()} />)
    // The inline link is preserved for non-file previews (scoping guard).
    expect(screen.getByText("the doc")).toBeInTheDocument()
  })

  test("replies render the decision marker but no Reply action", () => {
    const reply = buildComment({ id: "r1", parent_id: "p1", user: buildUser({ id: "viewer" }) })
    render(<Comment comment={reply} ctx={buildCtx()} isReply />)
    expect(screen.queryByText("Reply")).not.toBeInTheDocument()
    // Any workspace member can mark a reply as a decision (R5), so the marker shows.
    expect(screen.getByRole("button", { name: /Decide/ })).toBeInTheDocument()
  })
})

// On mobile the hover overflow menu and reaction tooltip are unreachable, so a
// long-press opens the action sheet instead. Same wiring for both comment levels.
describe("Comment on mobile (long-press action sheet)", () => {
  function longPress(el: Element) {
    // Fake timers come from the top-level beforeEach; just advance past the
    // useLongPress 500ms threshold.
    fireEvent.touchStart(el)
    act(() => {
      vi.advanceTimersByTime(500)
    })
  }

  beforeEach(() => {
    document.documentElement.dataset.isMobile = "true"
  })
  afterEach(() => {
    delete document.documentElement.dataset.isMobile
  })

  test("hides the hover overflow menu (its actions move into the sheet)", () => {
    render(<Comment comment={buildComment()} ctx={buildCtx()} />)
    expect(screen.queryByRole("button", { name: "Comment actions" })).not.toBeInTheDocument()
  })

  test("long-pressing the comment opens the sheet listing who reacted", () => {
    const comment = buildComment({
      content: "Hello world",
      reactions: { thumbs_up: [{ id: "u2", display_name: "Bob" }] },
    })
    render(<Comment comment={comment} ctx={buildCtx()} />)

    longPress(screen.getByText("Hello world"))

    expect(screen.getByRole("dialog", { name: "Comment actions" })).toBeInTheDocument()
    expect(screen.getByText("Bob")).toBeInTheDocument()
  })

  test("authors get Edit and Delete in the sheet; others do not", () => {
    const mine = buildComment({ content: "Mine", user: buildUser({ id: "viewer" }) })
    render(<Comment comment={mine} ctx={buildCtx()} />)
    longPress(screen.getByText("Mine"))
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument()

    cleanup()
    const theirs = buildComment({ content: "Theirs", user: buildUser({ id: "someone-else" }) })
    render(<Comment comment={theirs} ctx={buildCtx()} />)
    longPress(screen.getByText("Theirs"))
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument()
  })

  test("replies open the same sheet on long-press", () => {
    const reply = buildComment({ id: "r1", parent_id: "p1", content: "A reply" })
    render(<Comment comment={reply} ctx={buildCtx()} isReply />)
    longPress(screen.getByText("A reply"))
    expect(screen.getByRole("dialog", { name: "Comment actions" })).toBeInTheDocument()
  })
})
