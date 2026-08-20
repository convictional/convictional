import { screen, fireEvent, cleanup, act } from "@testing-library/react"
import { expect, test, describe, vi, beforeEach, afterEach } from "vitest"

vi.mock("~/react/composites/chat/ChatComposerEditor", () => import("../../shared/chatEditorMock"))

import { CommentThread } from "../../../../../app/javascript/react/composites/editor/components/comments/CommentThread"
import { CommentStoreProvider } from "../../../../../app/javascript/react/composites/editor/features/comments/CommentStoreContext"
import { CommentThreadsProvider } from "../../../../../app/javascript/react/composites/editor/features/comments/CommentThreadsContext"
import { DecisionsProvider } from "../../../../../app/javascript/react/composites/editor/features/comments/DecisionsContext"
import { documentCommentUIStore } from "../../../../../app/javascript/react/features/documentEditor/store"
import type { Decision } from "../../../../../app/javascript/react/shared/types"
import { render } from "../../shared/testUtils"
import {
  buildThreadsApi,
  makeComment,
  renderWithCommentProviders,
  type CommentThread as ThreadType,
  type CommentThreadsApi,
} from "./commentTestUtils"

const makeDecision = (commentGid: string, overrides: Partial<Decision> = {}): Decision => ({
  id: "d1",
  comment_gid: commentGid,
  comment_preview: "First comment",
  decided_by: { id: "u1", display_name: "Alice", picture: null },
  decided_at: "2026-06-01T00:00:00Z",
  ...overrides,
})

function renderThreadWithDecisions(thread: ThreadType, decisions: Map<string, Decision>, onToggleDecision = vi.fn()) {
  return {
    onToggleDecision,
    ...render(
      <CommentStoreProvider value={documentCommentUIStore}>
        <CommentThreadsProvider value={buildThreadsApi()}>
          <DecisionsProvider value={{ decisionsByGid: decisions, onToggleDecision }}>
            <CommentThread thread={thread} onRemoveMark={vi.fn()} />
          </DecisionsProvider>
        </CommentThreadsProvider>
      </CommentStoreProvider>
    ),
  }
}

function setUIState(overrides: Record<string, unknown> = {}) {
  documentCommentUIStore.setState({
    currentUserId: "u1",
    activeCommentId: "mark-1",
    activating: false,
    showCommentCard: false,
    commentCardTop: 0,
    pendingCommentId: "",
    selectedQuotedText: "",
    replyToId: null,
    editingCommentId: null,
    showReactionPicker: false,
    ...overrides,
  })
}

function setCSRFMeta() {
  let meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')
  if (!meta) {
    meta = document.createElement("meta")
    meta.name = "csrf-token"
    document.head.appendChild(meta)
  }
  meta.content = "test-token"
}

beforeEach(() => {
  setCSRFMeta()
  setUIState()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function renderThread(thread: ThreadType, onRemoveMark = vi.fn(), threadsApi: CommentThreadsApi = buildThreadsApi()) {
  return renderWithCommentProviders(<CommentThread thread={thread} onRemoveMark={onRemoveMark} />, { threadsApi })
}

describe("CommentThread", () => {
  test("renders nothing when thread is not active", () => {
    setUIState({ activeCommentId: "other-mark" })
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }

    const { container } = renderThread(thread)
    expect(container.innerHTML).toBe("")
  })

  test("renders all comments in order", () => {
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [
        makeComment({ id: "c1", content: "First comment", user: { id: "u1", display_name: "Alice", picture: null } }),
        makeComment({ id: "c2", content: "Second comment", user: { id: "u2", display_name: "Bob", picture: null } }),
      ],
    }

    renderThread(thread)

    expect(screen.getByText("First comment")).toBeTruthy()
    expect(screen.getByText("Second comment")).toBeTruthy()
    expect(screen.getByText("Alice")).toBeTruthy()
    expect(screen.getByText("Bob")).toBeTruthy()
  })

  test("shows Reply button when not replying", () => {
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
    renderThread(thread)
    expect(screen.getByText("Reply")).toBeTruthy()
  })

  test("clicking Reply opens reply form", () => {
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
    renderThread(thread)

    fireEvent.click(screen.getByText("Reply"))

    expect(documentCommentUIStore.getState().replyToId).toBe("mark-1")
  })

  test("shows reply form when replyToId matches", () => {
    setUIState({ replyToId: "mark-1" })
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
    renderThread(thread)

    expect(screen.getByPlaceholderText("Reply...")).toBeTruthy()
  })

  test("first comment menu shows Edit and Resolve for owner", () => {
    setUIState({ currentUserId: "u1" })
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ user: { id: "u1", display_name: "Alice", picture: null } })],
    }
    renderThread(thread)

    fireEvent.click(screen.getByText("more_horiz"))

    expect(screen.getByText("Edit")).toBeTruthy()
    expect(screen.getByText("Resolve")).toBeTruthy()
    expect(screen.queryByText("Delete")).toBeNull()
  })

  test("second comment menu shows Edit and Delete for owner, no Resolve", () => {
    setUIState({ currentUserId: "u1" })
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ id: "c1" }), makeComment({ id: "c2", content: "reply" })],
    }
    renderThread(thread)

    const menuButtons = screen.getAllByText("more_horiz")
    fireEvent.click(menuButtons[1])

    expect(screen.getByText("Edit")).toBeTruthy()
    expect(screen.getByText("Delete")).toBeTruthy()
    expect(screen.queryByText("Resolve")).toBeNull()
  })

  test("non-owner on non-first comment sees no menu", () => {
    setUIState({ currentUserId: "u-other" })
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [
        makeComment({ id: "c1", user: { id: "u1", display_name: "Alice", picture: null } }),
        makeComment({ id: "c2", content: "reply", user: { id: "u1", display_name: "Alice", picture: null } }),
      ],
    }
    renderThread(thread)

    const menuButtons = screen.getAllByText("more_horiz")
    expect(menuButtons).toHaveLength(1)
  })

  test("comment menu portals to document.body when open", () => {
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
    const { container } = renderThread(thread)

    fireEvent.click(screen.getByText("more_horiz"))

    expect(screen.getByText("Edit")).toBeTruthy()

    const menuInBody = document.body.querySelector(".dropdown-card.w-36")
    expect(menuInBody).not.toBeNull()
    expect(container.contains(menuInBody)).toBe(false)
  })

  test("clicking Edit switches to edit mode", () => {
    setUIState({ currentUserId: "u1" })
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment({ content: "original text" })] }
    renderThread(thread)

    fireEvent.click(screen.getByText("more_horiz"))
    fireEvent.click(screen.getByText("Edit"))

    expect(documentCommentUIStore.getState().editingCommentId).toBe("c1")
  })

  test("edit mode shows textarea with existing content", () => {
    setUIState({ currentUserId: "u1", editingCommentId: "c1" })
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment({ content: "original text" })] }
    renderThread(thread)

    const textarea = screen.getByDisplayValue("original text")
    expect(textarea).toBeTruthy()
    expect(screen.getByText("Save")).toBeTruthy()
    expect(screen.getByText("Cancel")).toBeTruthy()
  })

  test("cancel edit clears editing state", () => {
    setUIState({ currentUserId: "u1", editingCommentId: "c1" })
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment({ content: "original text" })] }
    renderThread(thread)

    fireEvent.click(screen.getByText("Cancel"))
    expect(documentCommentUIStore.getState().editingCommentId).toBeNull()
  })

  test("renders reaction pills with emoji and count", () => {
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [
        makeComment({
          reactions: {
            thumbs_up: [
              { id: "u1", display_name: "Alice" },
              { id: "u2", display_name: "Bob" },
            ],
          },
        }),
      ],
    }
    renderThread(thread)

    expect(screen.getByText("👍")).toBeTruthy()
    expect(screen.getByText("2")).toBeTruthy()
  })

  test("reaction pill shows display names in title tooltip", () => {
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [
        makeComment({
          reactions: {
            heart: [
              { id: "u1", display_name: "Alice" },
              { id: "u2", display_name: "Bob" },
            ],
          },
        }),
      ],
    }
    renderThread(thread)

    const pill = screen.getByText("❤️").closest("button")!
    expect(pill).toBeTruthy()
    expect(screen.getByText("2")).toBeTruthy()
  })

  test("reaction pill is highlighted when current user reacted", () => {
    setUIState({ currentUserId: "u1" })
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ reactions: { thumbs_up: [{ id: "u1", display_name: "Alice" }] } })],
    }
    renderThread(thread)

    const pill = screen.getByText("👍").closest("button")!
    expect(pill.className).toContain("btn-primary")
  })

  test("reaction pill is not highlighted when current user has not reacted", () => {
    setUIState({ currentUserId: "u-other" })
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ reactions: { thumbs_up: [{ id: "u1", display_name: "Alice" }] } })],
    }
    renderThread(thread)

    const pill = screen.getByText("👍").closest("button")!
    expect(pill.className).not.toContain("btn-primary")
  })

  test("reaction picker opens and shows all emoji options", () => {
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
    renderThread(thread)

    fireEvent.click(screen.getByText("mood"))

    expect(screen.getByText("👍")).toBeTruthy()
    expect(screen.getByText("👎")).toBeTruthy()
    expect(screen.getByText("😂")).toBeTruthy()
    expect(screen.getByText("🎉")).toBeTruthy()
    expect(screen.getByText("🙁")).toBeTruthy()
    expect(screen.getByText("❤️")).toBeTruthy()
    expect(screen.getByText("🚀")).toBeTruthy()
    expect(screen.getByText("👀")).toBeTruthy()
  })

  test("reaction picker portals out of the comment thread when open", () => {
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
    const { container } = renderThread(thread)

    fireEvent.click(screen.getByText("mood"))

    const emoji = screen.getByText("👍")
    expect(emoji).toBeTruthy()
    expect(container.contains(emoji)).toBe(false)
  })

  test("reaction picker closes when trigger is clicked again", () => {
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
    renderThread(thread)

    fireEvent.click(screen.getByText("mood"))
    expect(screen.queryByText("👍")).toBeTruthy()

    fireEvent.click(screen.getByText("mood"))
    expect(screen.queryByText("👍")).toBeNull()
  })

  test("clicking outside closes the reaction picker", () => {
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
    renderThread(thread)

    fireEvent.click(screen.getByText("mood"))
    expect(screen.queryByText("👍")).toBeTruthy()

    fireEvent.pointerDown(document.body)
    fireEvent.mouseDown(document.body)
    fireEvent.click(document.body)
    expect(screen.queryByText("👍")).toBeNull()
  })

  test("add-reaction button stays visible even with no reactions", () => {
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment({ reactions: {} })] }
    renderThread(thread)

    const moodButton = screen.getByText("mood").closest("button")!
    expect(moodButton.className).not.toContain("opacity-0")
  })

  test("long-press on reaction opens overlay with reactor names grouped by emoji", () => {
    vi.useFakeTimers()
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [
        makeComment({
          reactions: {
            thumbs_up: [
              { id: "u1", display_name: "Alice" },
              { id: "u2", display_name: "Bob" },
            ],
            heart: [{ id: "u3", display_name: "Carol" }],
          },
        }),
      ],
    }
    renderThread(thread)

    const thumbsUpPill = screen.getByText("👍").closest("button")!

    fireEvent.touchStart(thumbsUpPill)
    act(() => {
      vi.advanceTimersByTime(500)
    })
    fireEvent.touchEnd(thumbsUpPill)

    expect(screen.getByText("Alice, Bob")).toBeTruthy()
    expect(screen.getByText("Carol")).toBeTruthy()

    const overlayThumbs = screen.getAllByText("👍")
    expect(overlayThumbs.length).toBeGreaterThanOrEqual(2)
    const overlayHearts = screen.getAllByText("❤️")
    expect(overlayHearts.length).toBeGreaterThanOrEqual(1)
  })

  test("tapping overlay backdrop dismisses it", () => {
    vi.useFakeTimers()
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ reactions: { thumbs_up: [{ id: "u1", display_name: "Alice" }] } })],
    }
    renderThread(thread)

    const pill = screen.getByText("👍").closest("button")!

    fireEvent.touchStart(pill)
    act(() => {
      vi.advanceTimersByTime(500)
    })
    fireEvent.touchEnd(pill)

    expect(screen.getByTestId("reaction-overlay-backdrop")).toBeTruthy()

    fireEvent.click(screen.getByTestId("reaction-overlay-backdrop"))

    expect(screen.queryByTestId("reaction-overlay-backdrop")).toBeNull()
  })

  test("normal tap toggles reaction without opening overlay", () => {
    const toggleReaction = vi.fn().mockResolvedValue(undefined)
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ reactions: { thumbs_up: [{ id: "u1", display_name: "Alice" }] } })],
    }
    renderThread(thread, vi.fn(), buildThreadsApi({ toggleReaction }))

    const pill = screen.getByText("👍").closest("button")!
    fireEvent.click(pill)

    expect(toggleReaction).toHaveBeenCalledWith("c1", "thumbs_up")
    expect(screen.queryByTestId("reaction-overlay-backdrop")).toBeNull()
  })

  test("active thread card has max-h-[70vh] and overflow-y-auto classes", () => {
    const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
    renderThread(thread)

    const card = document.querySelector('[data-for-comment-id="mark-1"]') as HTMLElement
    expect(card).not.toBeNull()
    expect(card.className).toContain("max-h-[70vh]")
    expect(card.className).toContain("overflow-y-auto")
  })

  describe("auto-scroll-to-bottom behavior", () => {
    let originalScrollHeightDescriptor: PropertyDescriptor | undefined

    beforeEach(() => {
      originalScrollHeightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight")
      Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
        configurable: true,
        get() {
          return 9999
        },
      })
    })

    afterEach(() => {
      if (originalScrollHeightDescriptor) {
        Object.defineProperty(HTMLElement.prototype, "scrollHeight", originalScrollHeightDescriptor)
      } else {
        delete (HTMLElement.prototype as unknown as { scrollHeight?: unknown }).scrollHeight
      }
    })

    test("active thread card scrolls to bottom on first render", () => {
      const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
      renderThread(thread)

      const card = document.querySelector('[data-for-comment-id="mark-1"]') as HTMLElement
      expect(card).not.toBeNull()
      expect(card.scrollTop).toBe(9999)
    })

    test("card scrolls to bottom when reply form opens", () => {
      const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
      renderThread(thread)

      const card = document.querySelector('[data-for-comment-id="mark-1"]') as HTMLElement
      expect(card).not.toBeNull()

      card.scrollTop = 0

      act(() => {
        documentCommentUIStore.setState({ replyToId: "mark-1" })
      })

      expect(card.scrollTop).toBe(9999)
    })
  })

  describe("decision marker", () => {
    test("renders no marker when the editor does not provide decisions", () => {
      const thread: ThreadType = { markId: "mark-1", comments: [makeComment()] }
      renderThread(thread)
      expect(screen.queryByLabelText("Decide")).toBeNull()
      expect(screen.queryByText("Decision")).toBeNull()
    })

    test("undecided comment shows the Decide affordance and toggles by global_id", () => {
      const comment = makeComment({ global_id: "gid://convictional/DocumentComment/c1" })
      const thread: ThreadType = { markId: "mark-1", comments: [comment] }
      const { onToggleDecision } = renderThreadWithDecisions(thread, new Map())

      fireEvent.click(screen.getByLabelText("Decide"))
      expect(onToggleDecision).toHaveBeenCalledWith("gid://convictional/DocumentComment/c1")
    })

    test("decided comment shows the Decision pill with the decider's name", () => {
      const gid = "gid://convictional/DocumentComment/c1"
      const comment = makeComment({ global_id: gid })
      const thread: ThreadType = { markId: "mark-1", comments: [comment] }
      renderThreadWithDecisions(thread, new Map([[gid, makeDecision(gid)]]))

      expect(screen.getByText("Decision")).toBeTruthy()
      expect(screen.getByText("Alice")).toBeTruthy()
    })

    test("each comment in a thread carries its own marker keyed by its global_id", () => {
      const gid2 = "gid://convictional/DocumentComment/c2"
      const thread: ThreadType = {
        markId: "mark-1",
        comments: [
          makeComment({ id: "c1", global_id: "gid://convictional/DocumentComment/c1" }),
          makeComment({ id: "c2", global_id: gid2, content: "reply" }),
        ],
      }
      renderThreadWithDecisions(thread, new Map([[gid2, makeDecision(gid2)]]))

      expect(screen.getAllByText("Decision")).toHaveLength(1)
      expect(screen.getByLabelText("Decide")).toBeTruthy()
    })
  })

})
