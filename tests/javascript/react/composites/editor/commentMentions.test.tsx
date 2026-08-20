import { screen, cleanup } from "@testing-library/react"
import { expect, test, describe, vi, beforeEach, afterEach } from "vitest"

import { CommentThread } from "../../../../../app/javascript/react/composites/editor/components/comments/CommentThread"
import { documentCommentUIStore } from "../../../../../app/javascript/react/features/documentEditor/store"
import { makeComment, renderWithCommentProviders, type CommentThread as ThreadType } from "./commentTestUtils"

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

beforeEach(() => {
  setUIState()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function renderThread(thread: ThreadType) {
  return renderWithCommentProviders(<CommentThread thread={thread} onRemoveMark={vi.fn()} />)
}

// Comments render as markdown, and @[Name] mentions become a styled @Name span.
describe("comment mention rendering", () => {
  test("renders @[Name] as styled mention text", () => {
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ content: "Hey @[Alice Admin] thoughts?" })],
    }
    renderThread(thread)

    const mention = screen.getByText("@Alice Admin")
    expect(mention.tagName).toBe("SPAN")
    expect(mention.className).toContain("text-info-content")
    expect(screen.getByText(/thoughts\?/)).toBeTruthy()
  })

  test("renders multiple mentions in same comment", () => {
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ content: "@[Alice Admin] and @[Bob Builder] please review" })],
    }
    renderThread(thread)

    expect(screen.getByText("@Alice Admin")).toBeTruthy()
    expect(screen.getByText("@Bob Builder")).toBeTruthy()
    expect(screen.getByText(/please review/)).toBeTruthy()
  })

  test("renders plain text without mentions unchanged", () => {
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ content: "Just a normal comment" })],
    }
    renderThread(thread)

    expect(screen.getByText("Just a normal comment")).toBeTruthy()
  })

  test("renders markdown formatting", () => {
    const thread: ThreadType = {
      markId: "mark-1",
      comments: [makeComment({ content: "this is **bold** text" })],
    }
    renderThread(thread)

    const bold = screen.getByText("bold")
    expect(bold.tagName).toBe("STRONG")
  })
})
