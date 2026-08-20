import { renderHook } from "@testing-library/react"
import { EditorState } from "prosemirror-state"
import { EditorView } from "prosemirror-view"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { useArrowUpToEdit } from "../../../../../app/javascript/react/composites/editor/features/useArrowUpToEdit"
import { schema } from "../../../../../app/javascript/richText/schema"

describe("useArrowUpToEdit", () => {
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

  function setup(opts: { content?: string; onEditPrevious?: () => boolean }) {
    const onEditPrevious = opts.onEditPrevious ?? vi.fn(() => true)
    const { result } = renderHook(() => useArrowUpToEdit({ onEditPrevious }))
    const plugin = result.current.plugins[0]
    const paragraph = opts.content
      ? schema.node("paragraph", null, [schema.text(opts.content)])
      : schema.node("paragraph")
    const doc = schema.node("doc", null, [paragraph])
    const state = EditorState.create({ doc, plugins: [plugin] })
    view = new EditorView(container, { state })
    const handler = plugin.props.handleKeyDown!
    return { view, handler, onEditPrevious }
  }

  function pressArrowUp(view: EditorView, init: KeyboardEventInit = {}): boolean {
    const event = new KeyboardEvent("keydown", { key: "ArrowUp", ...init })
    const handled = view.someProp("handleKeyDown", f => f(view, event))
    return handled === true
  }

  test("triggers callback and consumes event when editor is empty", () => {
    const onEditPrevious = vi.fn(() => true)
    const { view } = setup({ onEditPrevious })
    expect(pressArrowUp(view)).toBe(true)
    expect(onEditPrevious).toHaveBeenCalledOnce()
  })

  test("does not trigger when editor has content", () => {
    const onEditPrevious = vi.fn(() => true)
    const { view } = setup({ content: "hello", onEditPrevious })
    expect(pressArrowUp(view)).toBe(false)
    expect(onEditPrevious).not.toHaveBeenCalled()
  })

  test("does not trigger when modifier keys are held", () => {
    const onEditPrevious = vi.fn(() => true)
    const { view } = setup({ onEditPrevious })
    for (const init of [{ shiftKey: true }, { altKey: true }, { metaKey: true }, { ctrlKey: true }]) {
      expect(pressArrowUp(view, init)).toBe(false)
    }
    expect(onEditPrevious).not.toHaveBeenCalled()
  })

  test("does not consume the event when callback returns false (no message to edit)", () => {
    const onEditPrevious = vi.fn(() => false)
    const { view } = setup({ onEditPrevious })
    expect(pressArrowUp(view)).toBe(false)
    expect(onEditPrevious).toHaveBeenCalledOnce()
  })

  test("ignores non-ArrowUp keys", () => {
    const onEditPrevious = vi.fn(() => true)
    const { view } = setup({ onEditPrevious })
    for (const key of ["ArrowDown", "Enter", "Escape", "a"]) {
      const event = new KeyboardEvent("keydown", { key })
      const handled = view.someProp("handleKeyDown", f => f(view, event))
      expect(handled !== true).toBe(true)
    }
    expect(onEditPrevious).not.toHaveBeenCalled()
  })

  test("treats whitespace-only content as empty", () => {
    const onEditPrevious = vi.fn(() => true)
    const { view } = setup({ content: "   ", onEditPrevious })
    expect(pressArrowUp(view)).toBe(true)
    expect(onEditPrevious).toHaveBeenCalledOnce()
  })
})
