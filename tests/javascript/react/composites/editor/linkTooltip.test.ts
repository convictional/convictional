import { expect, test, describe, it, vi, beforeEach } from "vitest"
import { EditorState, TextSelection } from "prosemirror-state"
import { render, screen, fireEvent } from "@testing-library/react"
import React from "react"

import { schema } from "../../../../../app/javascript/richText/schema"
import {
  findLinkAtCursor,
  linkClickPluginKey,
  createLinkClickPlugin,
  handleLinkClickEvent,
  findLinkAtDocPos,
} from "../../../../../app/javascript/react/composites/editor/features/useLinkTooltip"
import type { LinkInfo } from "../../../../../app/javascript/react/composites/editor/features/useLinkTooltip"
import { isValidHref } from "../../../../../app/javascript/react/composites/editor/features/linkUrls"
import { LinkTooltipBody } from "../../../../../app/javascript/react/composites/editor/components/LinkTooltip"

function createStateWithLink(text: string, href: string, cursorPos: number): EditorState {
  const linkMark = schema.marks.link.create({ href })
  const linkedText = schema.text(text, [linkMark])
  const doc = schema.node("doc", null, [schema.node("paragraph", null, [linkedText])])
  const state = EditorState.create({ doc, schema })
  return state.apply(state.tr.setSelection(TextSelection.near(state.doc.resolve(cursorPos))))
}

function createStateWithPlainText(text: string, cursorPos: number): EditorState {
  const doc = schema.node("doc", null, [schema.node("paragraph", null, [schema.text(text)])])
  const state = EditorState.create({ doc, schema })
  return state.apply(state.tr.setSelection(TextSelection.near(state.doc.resolve(cursorPos))))
}

function createStateWithPlugin(text: string, href: string, cursorPos: number): EditorState {
  const linkMark = schema.marks.link.create({ href })
  const linkedText = schema.text(text, [linkMark])
  const doc = schema.node("doc", null, [schema.node("paragraph", null, [linkedText])])
  const state = EditorState.create({ doc, schema, plugins: [createLinkClickPlugin()] })
  return state.apply(state.tr.setSelection(TextSelection.near(state.doc.resolve(cursorPos))))
}

function dispatchClickMeta(state: EditorState, info: LinkInfo | null): EditorState {
  return state.apply(state.tr.setMeta(linkClickPluginKey, info))
}

describe("isValidHref", () => {
  it("accepts http and https URLs and rejects everything else", () => {
    expect(isValidHref("https://example.com")).toBe(true)
    expect(isValidHref("http://example.com/path?q=1")).toBe(true)
    expect(isValidHref("  https://example.com  ")).toBe(true)
    expect(isValidHref("")).toBe(false)
    expect(isValidHref("   ")).toBe(false)
    expect(isValidHref("example.com")).toBe(false)
    expect(isValidHref("mailto:a@b.com")).toBe(false)
    expect(isValidHref("ftp://x.com")).toBe(false)
    expect(isValidHref("javascript:alert(1)")).toBe(false)
  })
})

describe("findLinkAtCursor", () => {
  test("returns the link mark when caret is anywhere inside it, null otherwise", () => {
    // doc: <p><a href="https://example.com">hello</a></p>
    // positions: 0=before doc, 1=before "hello", 6=after "hello"
    const expected = { from: 1, to: 6, href: "https://example.com" }

    for (const cursorPos of [1, 3, 6]) {
      const state = createStateWithLink("hello", "https://example.com", cursorPos)
      expect(findLinkAtCursor(state)).toEqual(expected)
    }

    // Distinct href round-trips through the mark attrs
    const otherHref = createStateWithLink("click me", "https://other-app.example/doc/123", 3)
    expect(findLinkAtCursor(otherHref)!.href).toBe("https://other-app.example/doc/123")

    // Plain text → null
    expect(findLinkAtCursor(createStateWithPlainText("hello world", 3))).toBeNull()

    // Range selection → null (callers expect only collapsed-cursor matches)
    const linkState = createStateWithLink("hello", "https://example.com", 2)
    const rangeState = linkState.apply(linkState.tr.setSelection(TextSelection.create(linkState.doc, 1, 4)))
    expect(findLinkAtCursor(rangeState)).toBeNull()
  })
})

describe("findLinkAtDocPos", () => {
  it("returns same result as findLinkAtCursor for matching positions", () => {
    const state = createStateWithLink("hello", "https://example.com", 3)

    const atMiddle = findLinkAtDocPos(state.doc, 3)
    expect(atMiddle).toEqual({ from: 1, to: 6, href: "https://example.com" })

    const atStart = findLinkAtDocPos(state.doc, 1)
    expect(atStart).toEqual({ from: 1, to: 6, href: "https://example.com" })

    const atEnd = findLinkAtDocPos(state.doc, 6)
    expect(atEnd).toEqual({ from: 1, to: 6, href: "https://example.com" })

    const plainState = createStateWithPlainText("hello world", 3)
    expect(findLinkAtDocPos(plainState.doc, 3)).toBeNull()
  })
})

describe("linkClickPlugin state", () => {
  it("sets active link when click meta is dispatched", () => {
    const state = createStateWithPlugin("hello", "https://example.com", 3)
    const newState = dispatchClickMeta(state, { from: 1, to: 6, href: "https://x" })
    expect(linkClickPluginKey.getState(newState)).toEqual({ from: 1, to: 6, href: "https://x" })
  })

  it("clears active link when meta:null is dispatched", () => {
    const state = createStateWithPlugin("hello", "https://example.com", 3)
    const withMeta = dispatchClickMeta(state, { from: 1, to: 6, href: "https://x" })
    const cleared = dispatchClickMeta(withMeta, null)
    expect(linkClickPluginKey.getState(cleared)).toBeNull()
  })

  it("clears active link when selection moves outside range", () => {
    // doc: <p><a href="https://x">hello world</a></p> → positions 1-12 are link range
    const state = createStateWithPlugin("hello world", "https://x", 3)
    const withMeta = dispatchClickMeta(state, { from: 1, to: 6, href: "https://x" })
    // Move selection to position 8 (outside [1,6])
    const moved = withMeta.apply(withMeta.tr.setSelection(TextSelection.near(withMeta.doc.resolve(8))))
    expect(linkClickPluginKey.getState(moved)).toBeNull()
  })

  it("keeps active link when selection stays inside range", () => {
    const state = createStateWithPlugin("hello", "https://example.com", 1)
    const withMeta = dispatchClickMeta(state, { from: 1, to: 6, href: "https://example.com" })
    const moved = withMeta.apply(withMeta.tr.setSelection(TextSelection.near(withMeta.doc.resolve(3))))
    expect(linkClickPluginKey.getState(moved)).toEqual({ from: 1, to: 6, href: "https://example.com" })
  })

  it("clears active link on document mutation", () => {
    const state = createStateWithPlugin("hello", "https://example.com", 3)
    const withMeta = dispatchClickMeta(state, { from: 1, to: 6, href: "https://example.com" })
    const mutated = withMeta.apply(withMeta.tr.insertText("x", 1))
    expect(linkClickPluginKey.getState(mutated)).toBeNull()
  })

  it("clears active link when removeMark and meta-null are chained", () => {
    const state = createStateWithPlugin("hello", "https://example.com", 3)
    const withMeta = dispatchClickMeta(state, { from: 1, to: 6, href: "https://example.com" })
    const tr = withMeta.tr.removeMark(1, 6, schema.marks.link).setMeta(linkClickPluginKey, null)
    const result = withMeta.apply(tr)
    expect(linkClickPluginKey.getState(result)).toBeNull()

    // Verify the link mark was removed from the first child of the paragraph
    const paragraph = result.doc.firstChild!
    const firstChild = paragraph.firstChild!
    const hasLinkMark = schema.marks.link.isInSet(firstChild.marks)
    expect(hasLinkMark).toBeFalsy()
  })
})

describe("handleLinkClickEvent", () => {
  function buildView() {
    const baseState = createStateWithLink("hello", "https://example.com", 1)
    const state = EditorState.create({ doc: baseState.doc, schema, plugins: [createLinkClickPlugin()] })

    const dom = document.createElement("div")
    const anchor = document.createElement("a")
    anchor.href = "https://example.com"
    anchor.textContent = "hello"
    dom.appendChild(anchor)

    const dispatch = vi.fn()
    const posAtDOM = vi.fn(() => 1)

    const view = {
      state,
      dom,
      dispatch,
      posAtDOM,
    } as any

    return { view, anchor, dispatch, posAtDOM }
  }

  function buildEvent(
    target: Element,
    overrides: Partial<{ metaKey: boolean; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; button: number }> = {}
  ) {
    return {
      target,
      metaKey: false,
      ctrlKey: false,
      altKey: false,
      shiftKey: false,
      button: 0,
      preventDefault: vi.fn(),
      ...overrides,
    } as any
  }

  it("returns false and skips preventDefault on modified clicks", () => {
    for (const overrides of [{ metaKey: true }, { ctrlKey: true }, { altKey: true }, { shiftKey: true }, { button: 1 }]) {
      const { view, anchor, dispatch } = buildView()
      const event = buildEvent(anchor, overrides)
      expect(handleLinkClickEvent(view, event)).toBe(false)
      expect(event.preventDefault).not.toHaveBeenCalled()
      expect(dispatch).not.toHaveBeenCalled()
    }
  })

  it("returns false when target has no anchor ancestor", () => {
    const { view, dispatch } = buildView()
    const div = document.createElement("div")
    view.dom.appendChild(div)
    const event = buildEvent(div)
    expect(handleLinkClickEvent(view, event)).toBe(false)
    expect(event.preventDefault).not.toHaveBeenCalled()
    expect(dispatch).not.toHaveBeenCalled()
  })

  it("returns false when anchor is not inside view.dom", () => {
    const { view, dispatch } = buildView()
    const outsideAnchor = document.createElement("a")
    outsideAnchor.href = "https://outside.com"
    // Note: not appended to view.dom
    const event = buildEvent(outsideAnchor)
    expect(handleLinkClickEvent(view, event)).toBe(false)
    expect(dispatch).not.toHaveBeenCalled()
  })

  it("returns true and dispatches on plain left-click", () => {
    const { view, anchor, dispatch } = buildView()
    const event = buildEvent(anchor)
    expect(handleLinkClickEvent(view, event)).toBe(true)
    expect(event.preventDefault).toHaveBeenCalledTimes(1)
    expect(dispatch).toHaveBeenCalledTimes(1)
    const tr = dispatch.mock.calls[0][0]
    expect(tr.getMeta(linkClickPluginKey)).toEqual({ from: 1, to: 6, href: "https://example.com" })
  })
})

describe("useLinkTooltipState merge (caret + click)", () => {
  it("uses caret link when no click state and selection inside a link", () => {
    const state = createStateWithPlugin("hello", "https://example.com", 3)
    expect(linkClickPluginKey.getState(state)).toBeNull()
    const caretLink = findLinkAtCursor(state)
    expect(caretLink).not.toBeNull()
    expect(caretLink!.href).toBe("https://example.com")
    expect(caretLink!.from).toBe(1)
    expect(caretLink!.to).toBe(6)
  })

  it("click state takes precedence when both are set", () => {
    // State A: caret inside link A (positions 1-6 = "hello" with href A)
    const state = createStateWithPlugin("hello", "https://a.com", 3)
    // Dispatch click meta for a different link B
    const newState = dispatchClickMeta(state, { from: 8, to: 14, href: "https://b.com" })

    // Click plugin state should reflect link B
    expect(linkClickPluginKey.getState(newState)).toEqual({ from: 8, to: 14, href: "https://b.com" })

    // Caret-based detection should still return link A (caret didn't move)
    const caretLink = findLinkAtCursor(newState)
    expect(caretLink).not.toBeNull()
    expect(caretLink!.href).toBe("https://a.com")
    expect(caretLink!.from).toBe(1)
    expect(caretLink!.to).toBe(6)
  })
})

describe("LinkTooltipBody view/edit modes", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function makeProps() {
    const mockRef = { current: null as HTMLDivElement | null }
    const mockState = {
      linkInfo: { from: 1, to: 6, href: "https://example.com" },
      visible: true,
      tooltipRef: mockRef,
    }
    const mockActions = {
      updateLink: vi.fn(),
      removeLink: vi.fn(),
    }
    return { mockState, mockActions }
  }

  it("renders view mode with URL, Open, Edit, Unlink", () => {
    const { mockState, mockActions } = makeProps()
    render(React.createElement(LinkTooltipBody, { state: mockState, actions: mockActions }))

    expect(screen.getByText("https://example.com")).toBeInTheDocument()
    expect(screen.getByText("open_in_new")).toBeInTheDocument()
    expect(screen.getByText("edit")).toBeInTheDocument()
    expect(screen.getByText("link_off")).toBeInTheDocument()
    expect(document.querySelector("input")).toBeNull()
  })

  it("switches to edit mode when Edit is clicked", () => {
    const { mockState, mockActions } = makeProps()
    render(React.createElement(LinkTooltipBody, { state: mockState, actions: mockActions }))

    const editIcon = screen.getByText("edit")
    fireEvent.click(editIcon.closest("button")!)

    expect(document.querySelector("input")).not.toBeNull()
    expect(screen.getByText("Save")).toBeInTheDocument()
    expect(screen.getByText("Cancel")).toBeInTheDocument()
    expect(screen.queryByText("link_off")).toBeNull()
  })

  it("saves the edited URL via Save button or Enter key", () => {
    for (const trigger of ["click-save", "enter-key"] as const) {
      const { mockState, mockActions } = makeProps()
      const { unmount } = render(React.createElement(LinkTooltipBody, { state: mockState, actions: mockActions }))
      fireEvent.click(screen.getByText("edit").closest("button")!)
      const input = document.querySelector("input")!
      fireEvent.change(input, { target: { value: "https://new.com" } })
      if (trigger === "click-save") {
        fireEvent.click(screen.getByText("Save"))
      } else {
        fireEvent.keyDown(input, { key: "Enter" })
      }
      expect(mockActions.updateLink).toHaveBeenCalledWith("https://new.com")
      unmount()
    }
  })

  it("disables Save and ignores Enter for invalid URLs", () => {
    const { mockState, mockActions } = makeProps()
    render(React.createElement(LinkTooltipBody, { state: mockState, actions: mockActions }))
    fireEvent.click(screen.getByText("edit").closest("button")!)
    const input = document.querySelector("input")!
    for (const invalid of ["", "  ", "example.com", "mailto:a@b.com", "ftp://x.com"]) {
      fireEvent.change(input, { target: { value: invalid } })
      const saveBtn = screen.getByText("Save") as HTMLButtonElement
      expect(saveBtn.disabled).toBe(true)
      fireEvent.keyDown(input, { key: "Enter" })
    }
    expect(mockActions.updateLink).not.toHaveBeenCalled()
  })

  it("returns to view without saving via Cancel button or Escape key", () => {
    for (const trigger of ["click-cancel", "escape-key"] as const) {
      const { mockState, mockActions } = makeProps()
      const { unmount } = render(React.createElement(LinkTooltipBody, { state: mockState, actions: mockActions }))
      fireEvent.click(screen.getByText("edit").closest("button")!)
      const input = document.querySelector("input")!
      fireEvent.change(input, { target: { value: "https://new.com" } })
      if (trigger === "click-cancel") {
        fireEvent.click(screen.getByText("Cancel"))
      } else {
        fireEvent.keyDown(input, { key: "Escape" })
      }
      expect(mockActions.updateLink).not.toHaveBeenCalled()
      expect(screen.getByText("link_off")).toBeInTheDocument()
      unmount()
    }
  })

  it("Escape in edit mode returns to view without closing the popover", () => {
    const { mockState, mockActions } = makeProps()
    render(React.createElement(LinkTooltipBody, { state: mockState, actions: mockActions }))
    fireEvent.click(screen.getByText("edit").closest("button")!)
    const input = document.querySelector("input")!
    expect(input).toBeInTheDocument()

    // The popover is closed by a document-level keydown listener in
    // useLinkTooltipState. If stopPropagation() is removed from the input's
    // Escape handler, the event bubbles to document and this spy fires —
    // pinning the fix.
    const docKeydownSpy = vi.fn()
    document.addEventListener("keydown", docKeydownSpy)

    try {
      fireEvent.keyDown(input, { key: "Escape", code: "Escape", bubbles: true })
      expect(docKeydownSpy).not.toHaveBeenCalled()
      expect(mockActions.updateLink).not.toHaveBeenCalled()
      expect(screen.getByText("link_off")).toBeInTheDocument()
    } finally {
      document.removeEventListener("keydown", docKeydownSpy)
    }
  })

  it("Unlink calls removeLink", () => {
    const { mockState, mockActions } = makeProps()
    render(React.createElement(LinkTooltipBody, { state: mockState, actions: mockActions }))

    fireEvent.click(screen.getByText("link_off").closest("button")!)
    expect(mockActions.removeLink).toHaveBeenCalled()
  })

  it("resets to view mode when active link href changes", () => {
    const { mockState, mockActions } = makeProps()
    const { rerender } = render(React.createElement(LinkTooltipBody, { state: mockState, actions: mockActions }))

    fireEvent.click(screen.getByText("edit").closest("button")!)
    expect(document.querySelector("input")).not.toBeNull()

    const newState = {
      ...mockState,
      linkInfo: { from: 1, to: 6, href: "https://different.com" },
    }
    rerender(React.createElement(LinkTooltipBody, { state: newState, actions: mockActions }))

    expect(document.querySelector("input")).toBeNull()
    expect(screen.getByText("link_off")).toBeInTheDocument()
  })
})
