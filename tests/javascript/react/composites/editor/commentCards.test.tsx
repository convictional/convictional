import { screen, fireEvent, waitFor, cleanup } from "@testing-library/react"
import { expect, test, describe, vi, beforeEach, afterEach } from "vitest"

vi.mock("~/react/composites/chat/ChatComposerEditor", () => import("../../shared/chatEditorMock"))

import { CommentCards } from "../../../../../app/javascript/react/composites/editor/components/comments/CommentCards"
import { documentCommentUIStore } from "../../../../../app/javascript/react/features/documentEditor/store"
import { buildThreadsApi, makeComment, renderWithCommentProviders, type CommentThreadsApi } from "./commentTestUtils"

function setCSRFMeta() {
  let meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')
  if (!meta) {
    meta = document.createElement("meta")
    meta.name = "csrf-token"
    document.head.appendChild(meta)
  }
  meta.content = "test-token"
}

function setUIState(overrides: Record<string, unknown> = {}) {
  documentCommentUIStore.setState({
    currentUserId: "u1",
    activeCommentId: null,
    activating: false,
    showCommentCard: false,
    commentCardTop: 100,
    pendingCommentId: "pending-1",
    selectedQuotedText: "selected text",
    replyToId: null,
    editingCommentId: null,
    showReactionPicker: false,
    ...overrides,
  })
}

const currentUser = { id: "u1", displayName: "Alice", picture: null }

beforeEach(() => {
  setCSRFMeta()
  setUIState()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function renderCards(props: Record<string, unknown> = {}, threadsApi: CommentThreadsApi = buildThreadsApi()) {
  return renderWithCommentProviders(
    <CommentCards
      currentUser={currentUser}
      onRemoveMark={vi.fn()}
      onCommitPendingComment={vi.fn()}
      onClearPendingComment={vi.fn()}
      {...props}
    />,
    {
      threadsApi,
    }
  )
}

describe("CommentCards", () => {
  test("does not render form when showCommentCard is false", () => {
    setUIState({ showCommentCard: false })
    renderCards()

    expect(screen.queryByPlaceholderText("Add a comment...")).toBeNull()
  })

  test("renders new comment form when showCommentCard is true", () => {
    setUIState({ showCommentCard: true })
    renderCards()

    expect(screen.getByPlaceholderText("Add a comment...")).toBeTruthy()
    expect(screen.getByText("Alice")).toBeTruthy()
    expect(screen.getByText("Comment")).toBeTruthy()
    expect(screen.getByText("Cancel")).toBeTruthy()
  })

  test("cancel clears the pending highlight and closes card", () => {
    setUIState({ showCommentCard: true, pendingCommentId: "pending-1" })
    const onClearPendingComment = vi.fn()
    renderCards({ onClearPendingComment })

    fireEvent.click(screen.getByText("Cancel"))

    expect(onClearPendingComment).toHaveBeenCalledWith("pending-1")
    expect(documentCommentUIStore.getState().showCommentCard).toBe(false)
  })

  test("submitting calls createComment, commits the pending mark, and closes card on success", async () => {
    setUIState({ showCommentCard: true, pendingCommentId: "pending-1", selectedQuotedText: "quoted" })
    const createComment = vi.fn().mockResolvedValue(makeComment({ comment_mark_id: "pending-1" }))
    const onCommitPendingComment = vi.fn()
    renderCards({ onCommitPendingComment }, buildThreadsApi({ createComment }))

    fireEvent.change(screen.getByPlaceholderText("Add a comment..."), { target: { value: "My comment" } })
    fireEvent.click(screen.getByText("Comment"))

    await waitFor(() => {
      expect(documentCommentUIStore.getState().showCommentCard).toBe(false)
    })
    expect(createComment).toHaveBeenCalledWith("My comment", "quoted", "pending-1")
    expect(onCommitPendingComment).toHaveBeenCalledWith("pending-1")
  })

  test("submitting keeps card open on API failure", async () => {
    setUIState({ showCommentCard: true, pendingCommentId: "pending-1", selectedQuotedText: "quoted" })
    const createComment = vi.fn().mockRejectedValue(new Error("server error"))
    renderCards({}, buildThreadsApi({ createComment }))

    fireEvent.change(screen.getByPlaceholderText("Add a comment..."), { target: { value: "My comment" } })
    fireEvent.click(screen.getByText("Comment"))

    await new Promise(r => setTimeout(r, 50))

    expect(documentCommentUIStore.getState().showCommentCard).toBe(true)
    expect(screen.getByPlaceholderText("Add a comment...")).toBeTruthy()
  })

  test("Escape key closes card and clears the pending highlight", () => {
    setUIState({ showCommentCard: true, pendingCommentId: "pending-1" })
    const onClearPendingComment = vi.fn()
    renderCards({ onClearPendingComment })

    fireEvent.keyDown(window, { key: "Escape" })

    expect(onClearPendingComment).toHaveBeenCalledWith("pending-1")
    expect(documentCommentUIStore.getState().showCommentCard).toBe(false)
  })

  test("renders existing thread cards", () => {
    const thread = { markId: "mark-1", comments: [makeComment({ content: "Existing comment" })] }
    setUIState({ activeCommentId: "mark-1" })
    renderCards({}, buildThreadsApi({ threads: [thread] }))

    expect(screen.getByText("Existing comment")).toBeTruthy()
  })
})
