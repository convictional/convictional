import { screen, fireEvent, cleanup } from "@testing-library/react"
import { expect, test, describe, vi, beforeEach, afterEach } from "vitest"

import { CommentGutter } from "../../../../../app/javascript/react/composites/editor/components/comments/CommentGutter"
import { documentCommentUIStore } from "../../../../../app/javascript/react/features/documentEditor/store"
import { buildThreadsApi, makeComment, renderWithCommentProviders, type CommentThreadsApi } from "./commentTestUtils"

function setUIState(overrides: Record<string, unknown> = {}) {
  documentCommentUIStore.setState({
    currentUserId: "u1",
    activeCommentId: null,
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

const REACTIONS = [
  { emoji: "👍", label: "thumbs up" },
  { emoji: "👎", label: "thumbs down" },
]

const defaultProps = {
  reactions: REACTIONS,
  onOpenComment: vi.fn(),
  onOpenReaction: vi.fn(),
  onAddReaction: vi.fn(),
  editorFocused: true,
  cursorBlockHasContent: true,
  cursorTop: 100,
}

beforeEach(() => {
  setUIState()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function renderGutter(props: Record<string, unknown> = {}, threadsApi: CommentThreadsApi = buildThreadsApi()) {
  return renderWithCommentProviders(<CommentGutter {...defaultProps} {...props} />, { threadsApi })
}

describe("CommentGutter", () => {
  test("shows cursor buttons when editor is focused with content", () => {
    renderGutter()

    expect(screen.getByTitle("Add comment")).toBeTruthy()
    expect(screen.getByTitle("Add reaction")).toBeTruthy()
  })

  test("hides cursor buttons when editor not focused", () => {
    renderGutter({ editorFocused: false })

    expect(screen.queryByTitle("Add comment")).toBeNull()
    expect(screen.queryByTitle("Add reaction")).toBeNull()
  })

  test("hides cursor buttons when block has no content", () => {
    renderGutter({ cursorBlockHasContent: false })

    expect(screen.queryByTitle("Add comment")).toBeNull()
  })

  test("hides cursor buttons when comment card is open", () => {
    setUIState({ showCommentCard: true })
    renderGutter()

    expect(screen.queryByTitle("Add comment")).toBeNull()
  })

  test("hides cursor buttons when a comment is active", () => {
    setUIState({ activeCommentId: "mark-1" })
    renderGutter()

    expect(screen.queryByTitle("Add comment")).toBeNull()
  })

  test("comment button calls onOpenComment", () => {
    const onOpenComment = vi.fn()
    renderGutter({ onOpenComment })

    fireEvent.mouseDown(screen.getByTitle("Add comment"))
    expect(onOpenComment).toHaveBeenCalledOnce()
  })

  test("reaction button calls onOpenReaction", () => {
    const onOpenReaction = vi.fn()
    renderGutter({ onOpenReaction })

    fireEvent.mouseDown(screen.getByTitle("Add reaction"))
    expect(onOpenReaction).toHaveBeenCalledOnce()
  })

  test("renders avatar for each thread", () => {
    const threads = [
      {
        markId: "mark-1",
        comments: [makeComment({ user: { id: "u1", display_name: "Alice", picture: null } })],
      },
      {
        markId: "mark-2",
        comments: [
          makeComment({ id: "c2", comment_mark_id: "mark-2", user: { id: "u2", display_name: "Bob", picture: null } }),
        ],
      },
    ]
    renderGutter({}, buildThreadsApi({ threads }))

    const avatarGroups = document.querySelectorAll("[data-avatar-for]")
    expect(avatarGroups).toHaveLength(2)
    expect(avatarGroups[0].getAttribute("data-avatar-for")).toBe("mark-1")
    expect(avatarGroups[1].getAttribute("data-avatar-for")).toBe("mark-2")
  })

  test("hides avatar when its thread is active", () => {
    const threads = [{ markId: "mark-1", comments: [makeComment()] }]
    setUIState({ activeCommentId: "mark-1" })
    renderGutter({}, buildThreadsApi({ threads }))

    const avatar = document.querySelector("[data-avatar-for='mark-1']") as HTMLElement
    expect(avatar.style.display).toBe("none")
  })

  test("clicking avatar activates the thread", () => {
    const threads = [{ markId: "mark-1", comments: [makeComment()] }]
    renderGutter({}, buildThreadsApi({ threads }))

    const avatar = document.querySelector("[data-avatar-for='mark-1']") as HTMLElement
    fireEvent.mouseDown(avatar)

    expect(documentCommentUIStore.getState().activeCommentId).toBe("mark-1")
  })

  test("deduplicates thread participants in avatars", () => {
    const threads = [
      {
        markId: "mark-1",
        comments: [
          makeComment({ id: "c1", user: { id: "u1", display_name: "Alice", picture: null } }),
          makeComment({ id: "c2", user: { id: "u1", display_name: "Alice", picture: null } }),
          makeComment({ id: "c3", user: { id: "u2", display_name: "Bob", picture: null } }),
        ],
      },
    ]
    renderGutter({}, buildThreadsApi({ threads }))

    // Should show 2 avatars (Alice + Bob), not 3
    const avatarGroup = document.querySelector("[data-avatar-for='mark-1']")!
    const avatarInitials = avatarGroup.querySelectorAll("span.uppercase")
    expect(avatarInitials).toHaveLength(2)
  })

  test("shows reaction picker when showReactionPicker is true", () => {
    setUIState({ showReactionPicker: true })
    renderGutter()

    expect(screen.getByLabelText("thumbs up")).toBeTruthy()
    expect(screen.getByLabelText("thumbs down")).toBeTruthy()
  })

  test("clicking reaction calls onAddReaction with emoji", () => {
    setUIState({ showReactionPicker: true })
    const onAddReaction = vi.fn()
    renderGutter({ onAddReaction })

    fireEvent.click(screen.getByLabelText("thumbs up"))
    expect(onAddReaction).toHaveBeenCalledWith("👍")
  })

  test("hides reaction picker when not open", () => {
    setUIState({ showReactionPicker: false })
    renderGutter()

    expect(screen.queryByLabelText("thumbs up")).toBeNull()
  })
})
