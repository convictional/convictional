import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { useScrollToHashComment } from "~/react/shared/hooks/useScrollToHashComment"

beforeEach(() => {
  // Run rAF synchronously so the hash handler resolves within act().
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    cb(0)
    return 0
  })
  window.location.hash = ""
  document.body.innerHTML = ""
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

function mountComment(id: string): HTMLElement {
  const el = document.createElement("div")
  el.setAttribute("data-comment-id", id)
  vi.spyOn(el, "scrollIntoView").mockImplementation(() => {})
  document.body.appendChild(el)
  return el
}

describe("useScrollToHashComment", () => {
  test("scrolls to and highlights the comment named by the hash once ready", () => {
    vi.useFakeTimers()
    // useFakeTimers re-mocks requestAnimationFrame; restore the synchronous stub.
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0)
      return 0
    })
    const el = mountComment("c1")
    window.location.hash = "#comment-c1"

    const { result } = renderHook(() => useScrollToHashComment(true))

    expect(el.scrollIntoView).toHaveBeenCalled()
    expect(result.current.highlightedId).toBe("c1")

    act(() => vi.advanceTimersByTime(2000))
    expect(result.current.highlightedId).toBeNull()
  })

  test("does nothing until ready", () => {
    const el = mountComment("c1")
    window.location.hash = "#comment-c1"

    const { result } = renderHook(() => useScrollToHashComment(false))

    expect(el.scrollIntoView).not.toHaveBeenCalled()
    expect(result.current.highlightedId).toBeNull()
  })

  test("no-ops for an unknown comment id", () => {
    window.location.hash = "#comment-missing"
    const { result } = renderHook(() => useScrollToHashComment(true))
    expect(result.current.highlightedId).toBeNull()
  })

  test("reacts to a later hashchange", () => {
    const el = mountComment("c5")
    const { result } = renderHook(() => useScrollToHashComment(true))

    act(() => {
      window.location.hash = "#comment-c5"
      window.dispatchEvent(new HashChangeEvent("hashchange"))
    })

    expect(el.scrollIntoView).toHaveBeenCalled()
    expect(result.current.highlightedId).toBe("c5")
  })

  test("scrollToComment jumps to and highlights an existing comment, no-ops otherwise", () => {
    vi.useFakeTimers()
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0)
      return 0
    })
    const el = mountComment("c9")
    const { result } = renderHook(() => useScrollToHashComment(true))

    act(() => result.current.scrollToComment("nope"))
    expect(result.current.highlightedId).toBeNull()

    act(() => result.current.scrollToComment("c9"))
    expect(el.scrollIntoView).toHaveBeenCalled()
    expect(result.current.highlightedId).toBe("c9")

    act(() => vi.advanceTimersByTime(2000))
    expect(result.current.highlightedId).toBeNull()
  })
})
