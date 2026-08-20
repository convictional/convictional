import { describe, expect, test } from "vitest"

import { createCommentUIStore } from "../../../../../app/javascript/react/composites/editor/features/comments/createCommentUIStore"

describe("createCommentUIStore", () => {
  test("init sets the viewer identity and resets UI state", () => {
    const store = createCommentUIStore()
    store.getState().openCommentCard(100, "quoted", "pending-1")
    store.getState().setActiveComment("mark-1")

    store.getState().init("u1", "Alice")

    const state = store.getState()
    expect(state.currentUserId).toBe("u1")
    expect(state.currentUserName).toBe("Alice")
    // Carried-over UI from a prior resource is cleared.
    expect(state.showCommentCard).toBe(false)
    expect(state.activeCommentId).toBeNull()
    expect(state.pendingCommentId).toBe("")
  })

  test("openCommentCard sets all related state", () => {
    const store = createCommentUIStore()
    store.getState().openCommentCard(100, "selected text", "pending-id")

    const state = store.getState()
    expect(state.showCommentCard).toBe(true)
    expect(state.commentCardTop).toBe(100)
    expect(state.selectedQuotedText).toBe("selected text")
    expect(state.pendingCommentId).toBe("pending-id")
  })

  test("closeCommentCard resets the form and clears the active comment", () => {
    const store = createCommentUIStore()
    store.getState().openCommentCard(100, "text", "id")
    store.getState().setActiveComment("mark-1")

    store.getState().closeCommentCard()

    const state = store.getState()
    expect(state.showCommentCard).toBe(false)
    expect(state.pendingCommentId).toBe("")
    expect(state.selectedQuotedText).toBe("")
    expect(state.activeCommentId).toBeNull()
  })

  test("closeReactionPicker resets picker state and clears the active comment", () => {
    const store = createCommentUIStore()
    store.getState().openReactionPicker("text", "pending-1")
    store.getState().setActiveComment("mark-1")

    store.getState().closeReactionPicker()

    const state = store.getState()
    expect(state.showReactionPicker).toBe(false)
    expect(state.pendingCommentId).toBe("")
    expect(state.activeCommentId).toBeNull()
  })
})
