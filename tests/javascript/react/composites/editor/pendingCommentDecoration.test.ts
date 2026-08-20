import { EditorState } from "prosemirror-state"
import { EditorView } from "prosemirror-view"
import { afterEach, describe, expect, test } from "vitest"

import {
  addPendingCommentDecoration,
  clearPendingCommentDecoration,
  commitPendingComment,
  pendingCommentPlugin,
} from "../../../../../app/javascript/react/composites/editor/features/comments/pendingCommentDecoration"
import { schema } from "../../../../../app/javascript/richText/schema"
import { getCommentMarkIds } from "../../../../../app/javascript/richText/schema/commentMark"

function mountView() {
  const doc = schema.node("doc", null, [schema.node("paragraph", null, [schema.text("hello world")])])
  const mount = document.createElement("div")
  document.body.appendChild(mount)
  const view = new EditorView(mount, { state: EditorState.create({ schema, doc, plugins: [pendingCommentPlugin] }) })
  return { view, mount }
}

function highlightCount(mount: HTMLElement, id: string) {
  return mount.querySelectorAll(`span.inline-comment-highlight[data-comment-id="${id}"]`).length
}

describe("pendingCommentDecoration", () => {
  let cleanupView: (() => void) | null = null

  afterEach(() => {
    cleanupView?.()
    cleanupView = null
  })

  // The core of the multi-user fix: while composing, the highlight is a local
  // decoration that never enters the shared doc, so it can't sync to peers (and
  // can't be stripped-and-broadcast by their orphan cleanup).
  test("pending decoration renders a highlight but adds no mark to the doc", () => {
    const { view, mount } = mountView()
    cleanupView = () => view.destroy()

    addPendingCommentDecoration(view, "pending-1", 1, 12)

    expect(highlightCount(mount, "pending-1")).toBe(1)
    expect(getCommentMarkIds(view.state.doc).size).toBe(0)
  })

  test("commit promotes the decoration to a real comment mark on the doc", () => {
    const { view, mount } = mountView()
    cleanupView = () => view.destroy()

    addPendingCommentDecoration(view, "pending-1", 1, 12)
    commitPendingComment(view, "pending-1")

    // The decoration is gone; the mark is now in the doc and will sync to peers.
    expect(getCommentMarkIds(view.state.doc).has("pending-1")).toBe(true)
    expect(highlightCount(mount, "pending-1")).toBe(1)
  })

  test("clear drops the pending decoration without touching the doc", () => {
    const { view, mount } = mountView()
    cleanupView = () => view.destroy()

    addPendingCommentDecoration(view, "pending-1", 1, 12)
    clearPendingCommentDecoration(view, "pending-1")

    expect(highlightCount(mount, "pending-1")).toBe(0)
    expect(getCommentMarkIds(view.state.doc).size).toBe(0)
  })

  test("commit anchors the mark at the decoration's mapped range after an edit", () => {
    const { view } = mountView()
    cleanupView = () => view.destroy()

    // Highlight "world" (positions 7-12).
    addPendingCommentDecoration(view, "pending-1", 7, 12)
    // A remote-style insertion before the highlight shifts it right by 6.
    view.dispatch(view.state.tr.insert(1, schema.text("PREFIX")))
    commitPendingComment(view, "pending-1")

    const marked: string[] = []
    view.state.doc.descendants(node => {
      if (node.marks.some(m => m.type === schema.marks.comment && m.attrs.commentId === "pending-1")) {
        marked.push(node.text ?? "")
      }
    })
    expect(marked.join("")).toBe("world")
  })
})
