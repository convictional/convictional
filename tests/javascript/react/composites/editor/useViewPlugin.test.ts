import { renderHook } from "@testing-library/react"
import { EditorState } from "prosemirror-state"
import { EditorView } from "prosemirror-view"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// Mock serialize so we can count how many times it's invoked per keystroke
// and avoid pulling the heavy markdown serializer into this test.
vi.mock("~/richText/schema", async () => {
  const actual = await vi.importActual<typeof import("~/richText/schema")>("~/richText/schema")
  return {
    ...actual,
    serialize: vi.fn(() => "serialized"),
  }
})

import { DEBOUNCE_MS, useViewPlugin } from "~/react/composites/editor/features/useViewPlugin"
import { schema, serialize } from "~/richText/schema"

const mockSerialize = vi.mocked(serialize)

describe("useViewPlugin", () => {
  let container: HTMLDivElement
  let view: EditorView | undefined

  beforeEach(() => {
    container = document.createElement("div")
    document.body.appendChild(container)
    mockSerialize.mockClear()
  })

  afterEach(() => {
    view?.destroy()
    view = undefined
    container?.remove()
    vi.useRealTimers()
  })

  function setup(onChange: (markdown: string) => void) {
    const { result } = renderHook(() => useViewPlugin({ onChange, debounceMs: DEBOUNCE_MS }))
    const plugin = result.current.plugins[0]
    const doc = schema.node("doc", null, [schema.node("paragraph")])
    const state = EditorState.create({ doc, plugins: [plugin] })
    view = new EditorView(container, { state })
    return { view, cancel: result.current.cancel }
  }

  function typeChar(view: EditorView, ch: string) {
    const tr = view.state.tr.insertText(ch)
    view.dispatch(tr)
  }

  test("debounces serialize/onChange across rapid keystrokes", () => {
    vi.useFakeTimers()
    const onChange = vi.fn()
    const { view } = setup(onChange)

    // Rapid keystrokes within the debounce window
    typeChar(view, "h")
    typeChar(view, "i")
    typeChar(view, "!")

    // Before the debounce fires nothing should have been serialized or emitted
    expect(mockSerialize).toHaveBeenCalledTimes(0)
    expect(onChange).toHaveBeenCalledTimes(0)

    vi.advanceTimersByTime(DEBOUNCE_MS)

    // Exactly one serialize and one onChange after the debounce, regardless of
    // how many keystrokes happened in the window.
    expect(mockSerialize).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenLastCalledWith("serialized")
  })

  test("subsequent burst of keystrokes triggers another debounced call", () => {
    vi.useFakeTimers()
    const onChange = vi.fn()
    const { view } = setup(onChange)

    typeChar(view, "a")
    vi.advanceTimersByTime(DEBOUNCE_MS)
    expect(onChange).toHaveBeenCalledTimes(1)

    typeChar(view, "b")
    typeChar(view, "c")
    expect(onChange).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(DEBOUNCE_MS)
    expect(onChange).toHaveBeenCalledTimes(2)
    expect(onChange).toHaveBeenLastCalledWith("serialized")
  })

  test("destroy flushes pending serialize (panel-close / route-change path)", () => {
    vi.useFakeTimers()
    const onChange = vi.fn()
    const { view } = setup(onChange)

    typeChar(view, "x")
    expect(onChange).toHaveBeenCalledTimes(0)

    // Unmount before the debounce fires — simulates the user closing the chat
    // panel within DEBOUNCE_MS of their last keystroke.
    view.destroy()

    expect(mockSerialize).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenLastCalledWith("serialized")

    // Pending timer must not also fire after destroy.
    vi.advanceTimersByTime(DEBOUNCE_MS * 2)
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  test("cancel() drops a pending serialize so a subsequent destroy doesn't flush it", () => {
    // Locks down the pre-send contract: chat composer calls cancel() before
    // sendMessage so the post-send remount's destroy() can't flush stale
    // pre-send markdown back into draftContent.
    vi.useFakeTimers()
    const onChange = vi.fn()
    const { view, cancel } = setup(onChange)

    typeChar(view, "x")
    expect(onChange).toHaveBeenCalledTimes(0)

    cancel()
    expect(mockSerialize).toHaveBeenCalledTimes(0)
    expect(onChange).toHaveBeenCalledTimes(0)

    // Pending timer must not fire after cancel.
    vi.advanceTimersByTime(DEBOUNCE_MS * 2)
    expect(onChange).toHaveBeenCalledTimes(0)

    // Destroy after cancel must also be silent.
    view.destroy()
    expect(mockSerialize).toHaveBeenCalledTimes(0)
    expect(onChange).toHaveBeenCalledTimes(0)
  })

  test("cancel() is a no-op when no debounce is pending", () => {
    vi.useFakeTimers()
    const onChange = vi.fn()
    const { view, cancel } = setup(onChange)

    typeChar(view, "x")
    vi.advanceTimersByTime(DEBOUNCE_MS)
    expect(onChange).toHaveBeenCalledTimes(1)
    mockSerialize.mockClear()

    cancel()
    expect(mockSerialize).toHaveBeenCalledTimes(0)
    expect(onChange).toHaveBeenCalledTimes(1)

    // After a no-op cancel, the next keystroke still debounces normally.
    typeChar(view, "y")
    vi.advanceTimersByTime(DEBOUNCE_MS)
    expect(onChange).toHaveBeenCalledTimes(2)
  })

  test("destroy is a no-op when no debounce is pending", () => {
    vi.useFakeTimers()
    const onChange = vi.fn()
    const { view } = setup(onChange)

    typeChar(view, "x")
    vi.advanceTimersByTime(DEBOUNCE_MS)
    expect(onChange).toHaveBeenCalledTimes(1)
    mockSerialize.mockClear()

    // No new keystrokes since the timer fired — destroy should not re-serialize.
    view.destroy()
    expect(mockSerialize).toHaveBeenCalledTimes(0)
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  test("plugin instance is referentially stable across hook re-renders", () => {
    const onChange = vi.fn()
    const { result, rerender } = renderHook(
      ({ cb }) => useViewPlugin({ onChange: cb, debounceMs: DEBOUNCE_MS }),
      {
        initialProps: { cb: onChange },
      }
    )
    const firstPlugin = result.current.plugins[0]

    // Re-render with a brand new onChange reference (simulates parent prop change).
    rerender({ cb: vi.fn() })
    rerender({ cb: vi.fn() })

    expect(result.current.plugins[0]).toBe(firstPlugin)
  })
})
