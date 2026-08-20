import { EditorState } from "prosemirror-state"
import { EditorView } from "prosemirror-view"
import { afterEach, beforeEach, describe, expect, test } from "vitest"

import { cleanupOrphanMarks } from "../../../../../app/javascript/react/composites/editor/features/comments/useCommentMarks"
import { getCommentMarkIds } from "../../../../../app/javascript/richText/schema/commentMark"
import type { CommentThread } from "../../../../../app/javascript/react/composites/editor/features/comments/commentThreads"
import { schema, plugins } from "../../../../../app/javascript/richText/schema"

function thread(markId: string): CommentThread {
  return { markId, comments: [] }
}

describe("cleanupOrphanMarks", () => {
  let container: HTMLDivElement
  let view: EditorView

  beforeEach(() => {
    container = document.createElement("div")
    document.body.appendChild(container)
  })

  afterEach(() => {
    view?.destroy()
    container?.remove()
  })

  function createView(content: string): void {
    const doc = schema.node("doc", null, [schema.node("paragraph", null, [schema.text(content)])])
    const state = EditorState.create({ doc, schema, plugins })
    view = new EditorView(container, { state })
  }

  function getCommentMarkType() {
    const markType = view.state.schema.marks.comment
    if (!markType) throw new Error("comment mark not registered on schema")
    return markType
  }

  // Pre-fix, a thread whose mark was missing from the doc but whose quoted_text
  // matched a substring would have had a mark planted via indexOf. The fix
  // removed that restoration loop — this test fails if it comes back.
  test("does NOT plant a mark for a thread whose text matches doc text (ghost-highlight regression)", () => {
    createView("foo bar foo baz")
    const markType = getCommentMarkType()

    const setupTr = view.state.tr.addMark(9, 12, markType.create({ commentId: "valid-mark" }))
    view.dispatch(setupTr)

    cleanupOrphanMarks(view, [thread("valid-mark"), thread("missing-mark")], null)

    const markIds = getCommentMarkIds(view.state.doc)
    expect(markIds.has("valid-mark")).toBe(true)
    expect(markIds.has("missing-mark")).toBe(false)
    expect(markIds.size).toBe(1)
  })

  test("removes orphan marks whose commentId does not match any thread", () => {
    createView("hello world")
    const markType = getCommentMarkType()

    const tr = view.state.tr
      .addMark(1, 6, markType.create({ commentId: "orphan-mark" }))
      .addMark(7, 12, markType.create({ commentId: "valid-thread" }))
    view.dispatch(tr)

    cleanupOrphanMarks(view, [thread("valid-thread")], null)

    const markIds = getCommentMarkIds(view.state.doc)
    expect(markIds.has("orphan-mark")).toBe(false)
    expect(markIds.has("valid-thread")).toBe(true)
    expect(markIds.size).toBe(1)
  })

  test("preserves the pending comment mark even when it has no thread yet", () => {
    createView("hello world")
    const markType = getCommentMarkType()

    const tr = view.state.tr.addMark(1, 6, markType.create({ commentId: "pending-mark" }))
    view.dispatch(tr)

    cleanupOrphanMarks(view, [], "pending-mark")

    const markIds = getCommentMarkIds(view.state.doc)
    expect(markIds.has("pending-mark")).toBe(true)
  })

  test("removes all marks when threads is empty", () => {
    createView("hello world")
    const markType = getCommentMarkType()
    const tr = view.state.tr.addMark(1, 6, markType.create({ commentId: "some-mark" }))
    view.dispatch(tr)

    cleanupOrphanMarks(view, [], null)

    expect(getCommentMarkIds(view.state.doc).size).toBe(0)
  })

  // After the fix, useCommentMarks passes `pendingFetchMarkIdsRef.current` as a fourth
  // argument so marks queued for the 500ms refetch debounce survive cleanup until
  // the fetch resolves and adds them to `threads`.
  test("does not strip a mark whose id is in pendingMarkIds even when threads is empty", () => {
    createView("hello world")
    const markType = getCommentMarkType()

    view.dispatch(view.state.tr.addMark(1, 6, markType.create({ commentId: "in-flight-mark" })))

    cleanupOrphanMarks(view, [], null, new Set(["in-flight-mark"]))

    expect(getCommentMarkIds(view.state.doc).has("in-flight-mark")).toBe(true)
  })

  test("strips genuine orphans even when pendingMarkIds contains other marks", () => {
    createView("hello world foo")
    const markType = getCommentMarkType()

    view.dispatch(
      view.state.tr
        .addMark(1, 6, markType.create({ commentId: "valid-thread" }))
        .addMark(7, 12, markType.create({ commentId: "in-flight-peer" }))
        .addMark(13, 16, markType.create({ commentId: "deleted-orphan" }))
    )

    // valid-thread is in threads; in-flight-peer is in pendingMarkIds (500ms window);
    // deleted-orphan is neither — it must be stripped.
    cleanupOrphanMarks(view, [thread("valid-thread")], null, new Set(["in-flight-peer"]))

    const ids = getCommentMarkIds(view.state.doc)
    expect(ids.has("valid-thread")).toBe(true)
    expect(ids.has("in-flight-peer")).toBe(true)
    expect(ids.has("deleted-orphan")).toBe(false)
  })
})
