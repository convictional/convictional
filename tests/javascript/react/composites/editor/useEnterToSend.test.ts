import { renderHook } from "@testing-library/react"
import { Node } from "prosemirror-model"
import { EditorState } from "prosemirror-state"
import { EditorView } from "prosemirror-view"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { useEnterToSend } from "../../../../../app/javascript/react/composites/editor/features/useEnterToSend"
import { schema } from "../../../../../app/javascript/richText/schema"

describe("useEnterToSend", () => {
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

  function setup(opts: { content?: string; doc?: Node; interceptEnter?: boolean; requireModifier?: boolean } = {}) {
    const onSend = vi.fn()
    const { result } = renderHook(() =>
      useEnterToSend({ onSend, interceptEnter: opts.interceptEnter, requireModifier: opts.requireModifier })
    )
    const plugin = result.current.plugins[0]
    const doc = opts.doc ?? paragraphDoc(opts.content)
    const state = EditorState.create({ doc, plugins: [plugin] })
    view = new EditorView(container, { state })
    return { view, onSend, feature: result.current }
  }

  const image = (src: string) => schema.node("image", { src })

  const paragraphDoc = (content?: string) => {
    const paragraph =
      content !== undefined ? schema.node("paragraph", null, [schema.text(content)]) : schema.node("paragraph")
    return schema.node("doc", null, [paragraph])
  }

  const codeBlockDoc = () => schema.node("doc", null, [schema.node("code_block", null, [schema.text("x")])])

  const listItemDoc = (itemType: "regular_list_item" | "task_list_item" = "regular_list_item") =>
    schema.node("doc", null, [
      schema.node("bullet_list", null, [
        schema.node(itemType, itemType === "task_list_item" ? { checked: false } : null, [
          schema.node("paragraph", null, [schema.text("x")]),
        ]),
      ]),
    ])

  function pressEnter(view: EditorView, init: KeyboardEventInit = {}): boolean {
    const event = new KeyboardEvent("keydown", { key: "Enter", ...init })
    const handled = view.someProp("handleKeyDown", f => f(view, event))
    return handled === true
  }

  // Default mode (chat): plain Enter sends; Shift+Enter defers to the keymap.
  describe("default mode", () => {
    test("plain Enter sends the content", () => {
      const { view, onSend } = setup({ content: "hello" })
      expect(pressEnter(view)).toBe(true)
      expect(onSend).toHaveBeenCalledExactlyOnceWith("hello")
    })

    test("plain Enter inside a code block defers and does not send", () => {
      const { view, onSend } = setup({ doc: codeBlockDoc() })
      expect(pressEnter(view)).toBe(false)
      expect(onSend).not.toHaveBeenCalled()
    })

    test.each(["regular_list_item", "task_list_item"] as const)(
      "plain Enter inside a %s defers and does not send",
      itemType => {
        const { view, onSend } = setup({ doc: listItemDoc(itemType) })
        expect(pressEnter(view)).toBe(false)
        expect(onSend).not.toHaveBeenCalled()
      }
    )

    test("Cmd+Enter and Ctrl+Enter submit even inside a code block", () => {
      const cmd = setup({ doc: codeBlockDoc() })
      expect(pressEnter(cmd.view, { metaKey: true })).toBe(true)
      expect(cmd.onSend).toHaveBeenCalled()

      const ctrl = setup({ doc: codeBlockDoc() })
      expect(pressEnter(ctrl.view, { ctrlKey: true })).toBe(true)
      expect(ctrl.onSend).toHaveBeenCalled()
    })

    // Shift+Enter is a new-block gesture owned by the shared keymap, not the send
    // feature: this plugin declines the key (so the keymap's Shift-Enter split
    // runs) and never sends. The block-splitting behavior itself is covered in
    // richText/schema/keymap.test.ts (getShiftEnterCommand).
    test("Shift+Enter defers to the keymap and does not send", () => {
      const { view, onSend } = setup({ content: "hello" })
      expect(pressEnter(view, { shiftKey: true })).toBe(false)
      expect(onSend).not.toHaveBeenCalled()
    })

    test("does not send when the editor is empty", () => {
      const { view, onSend } = setup({})
      pressEnter(view)
      expect(onSend).not.toHaveBeenCalled()
    })
  })

  // requireModifier mode (post comments, replies, edits): only Cmd/Ctrl+Enter
  // sends; plain Enter falls through for a newline.
  describe("requireModifier mode", () => {
    test("plain Enter falls through for a newline (does not send)", () => {
      const { view, onSend } = setup({ content: "hello", requireModifier: true })
      expect(pressEnter(view)).toBe(false)
      expect(onSend).not.toHaveBeenCalled()
    })

    test("Cmd+Enter sends the content", () => {
      const { view, onSend } = setup({ content: "hello", requireModifier: true })
      expect(pressEnter(view, { metaKey: true })).toBe(true)
      expect(onSend).toHaveBeenCalledExactlyOnceWith("hello")
    })

    test("Ctrl+Enter sends the content", () => {
      const { view, onSend } = setup({ content: "hello", requireModifier: true })
      expect(pressEnter(view, { ctrlKey: true })).toBe(true)
      expect(onSend).toHaveBeenCalledExactlyOnceWith("hello")
    })

    test("Shift+Enter does not send", () => {
      const { view, onSend } = setup({ content: "hello", requireModifier: true })
      expect(pressEnter(view, { shiftKey: true })).toBe(false)
      expect(onSend).not.toHaveBeenCalled()
    })
  })

  // Mobile: Enter is left to insert a newline; sending happens via send().
  test("does not intercept Enter when interceptEnter is false", () => {
    const { view, onSend } = setup({ content: "hello", interceptEnter: false })
    expect(pressEnter(view)).toBe(false)
    expect(pressEnter(view, { metaKey: true })).toBe(false)
    expect(onSend).not.toHaveBeenCalled()
  })

  // Uploading images leaves a trailing empty paragraph as a caret target (see attachments.ts). It
  // must not survive into the sent message as a blank line, but a real block after the images (a
  // typed caption) must be preserved.
  describe("trailing empty blocks", () => {
    test("strips the caret's empty paragraph left after an image upload", () => {
      const doc = schema.node("doc", null, [
        schema.node("paragraph", null, [image("/a"), image("/b")]),
        schema.node("paragraph"),
      ])
      const { view, onSend } = setup({ doc })
      expect(pressEnter(view)).toBe(true)
      // No trailing "<br />" — the images serialize as a single gallery-forming paragraph.
      expect(onSend).toHaveBeenCalledExactlyOnceWith("![](/a)![](/b)")
    })

    test("keeps a typed caption after images (both the gallery and the text survive)", () => {
      const doc = schema.node("doc", null, [
        schema.node("paragraph", null, [image("/a"), image("/b")]),
        schema.node("paragraph", null, [schema.text("nice pics")]),
      ])
      const { view, onSend } = setup({ doc })
      expect(pressEnter(view)).toBe(true)
      expect(onSend).toHaveBeenCalledExactlyOnceWith("![](/a)![](/b)\n\nnice pics")
    })
  })

  describe("send()", () => {
    test("submits the current content even when Enter is not intercepted", () => {
      const { onSend, feature } = setup({ content: "hello", interceptEnter: false })
      feature.send()
      expect(onSend).toHaveBeenCalledExactlyOnceWith("hello")
    })

    test("does nothing when the editor is empty", () => {
      const { onSend, feature } = setup({})
      feature.send()
      expect(onSend).not.toHaveBeenCalled()
    })
  })
})
