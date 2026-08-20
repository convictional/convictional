import { act } from "@testing-library/react"
import { describe, expect, test } from "vitest"

import type { CommentThread } from "~/react/composites/editor/features/comments/commentThreads"
import { createCommentUIStore } from "~/react/composites/editor/features/comments/createCommentUIStore"
import { useClearActiveCommentWhenGone } from "~/react/composites/editor/features/comments/useClearActiveCommentWhenGone"

import { renderHook } from "../../shared/testUtils"
import { makeComment } from "./commentTestUtils"

const threadFor = (markId: string): CommentThread => ({
  markId,
  comments: [makeComment({ comment_mark_id: markId })],
})

describe("useClearActiveCommentWhenGone", () => {
  test("clears the selection when its thread disappears", () => {
    const uiStore = createCommentUIStore()
    uiStore.getState().setActiveComment("m1")

    const { rerender } = renderHook(({ threads }) => useClearActiveCommentWhenGone(threads, uiStore), {
      initialProps: { threads: [threadFor("m1")] },
    })
    expect(uiStore.getState().activeCommentId).toBe("m1")

    act(() => rerender({ threads: [] }))
    expect(uiStore.getState().activeCommentId).toBeNull()
  })

  test("keeps the selection while its thread is still present", () => {
    const uiStore = createCommentUIStore()
    uiStore.getState().setActiveComment("m1")

    renderHook(() => useClearActiveCommentWhenGone([threadFor("m1")], uiStore))
    expect(uiStore.getState().activeCommentId).toBe("m1")
  })

  test("does nothing when no thread is active", () => {
    const uiStore = createCommentUIStore()

    renderHook(() => useClearActiveCommentWhenGone([], uiStore))
    expect(uiStore.getState().activeCommentId).toBeNull()
  })
})
