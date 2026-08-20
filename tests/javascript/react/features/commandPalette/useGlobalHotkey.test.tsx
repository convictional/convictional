import { cleanup, fireEvent, render } from "@testing-library/react"
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest"

import { useGlobalHotkey } from "../../../../../app/javascript/react/features/commandPalette/useGlobalHotkey"

// Stub navigator.platform so @github/hotkey's `Mod` alias resolves to a
// known modifier in the test environment. jsdom defaults vary; pinning it
// here keeps the tests deterministic regardless of the host machine.
beforeAll(() => {
  Object.defineProperty(window.navigator, "platform", { value: "Linux x86_64", configurable: true })
})

function Harness({ onHotkey }: { onHotkey: () => void }) {
  useGlobalHotkey(onHotkey)
  return null
}

describe("useGlobalHotkey", () => {
  afterEach(cleanup)

  // Regression: @github/hotkey's data-hotkey path ignores keydown events from
  // inputs / textareas / contenteditable, which blocked ⌘K from the chat
  // composer (auto-focused) and the document editor. A window-level handler
  // using eventToHotkeyString fixes it.
  test.each([
    ["plain input", () => Object.assign(document.createElement("input"), { type: "text" })],
    ["textarea", () => document.createElement("textarea")],
    [
      "contenteditable div",
      () => {
        const div = document.createElement("div")
        div.setAttribute("contenteditable", "true")
        return div
      },
    ],
  ])("fires Mod+K when focus is in %s", (_label, makeEl) => {
    const spy = vi.fn()
    render(<Harness onHotkey={spy} />)

    const focusable = makeEl()
    document.body.appendChild(focusable)
    focusable.focus()

    // Linux/Windows: Mod resolves to Control
    fireEvent.keyDown(window, { key: "k", ctrlKey: true })

    expect(spy).toHaveBeenCalledTimes(1)
    document.body.removeChild(focusable)
  })

  test("ignores plain k keypress", () => {
    const spy = vi.fn()
    render(<Harness onHotkey={spy} />)

    fireEvent.keyDown(window, { key: "k" })

    expect(spy).not.toHaveBeenCalled()
  })

  test("ignores wrong-modifier hotkey on this platform", () => {
    const spy = vi.fn()
    render(<Harness onHotkey={spy} />)

    // navigator.platform is Linux above, so Meta+k should NOT trigger.
    fireEvent.keyDown(window, { key: "k", metaKey: true })

    expect(spy).not.toHaveBeenCalled()
  })

  // Regression: ProseMirror plugins in the chat / doc editors can
  // stopPropagation on keydown. The window listener must run in the capture
  // phase so it fires before any descendant handler swallows the event.
  test("fires even if a descendant stops propagation in the bubble phase", () => {
    const spy = vi.fn()
    render(<Harness onHotkey={spy} />)

    const editor = document.createElement("div")
    editor.setAttribute("contenteditable", "true")
    editor.addEventListener("keydown", e => e.stopPropagation())
    document.body.appendChild(editor)
    editor.focus()

    editor.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }))

    expect(spy).toHaveBeenCalledTimes(1)
    document.body.removeChild(editor)
  })
})
