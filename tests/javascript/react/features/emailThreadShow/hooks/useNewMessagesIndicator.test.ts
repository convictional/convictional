import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { useNewMessagesIndicator } from "~/react/features/emailThreadShow/hooks/useNewMessagesIndicator"

afterEach(() => {
  vi.restoreAllMocks()
  // jsdom keeps the previous scrollY across tests — explicitly reset.
  window.scrollTo({ top: 0, behavior: "instant" })
})

describe("useNewMessagesIndicator", () => {
  it("notifyNewItem auto-scrolls when at the bottom", () => {
    // The scroll is deferred a frame so it reads scrollHeight after the new
    // item lays out; run the rAF callback synchronously to observe it.
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(cb => {
      cb(0)
      return 0
    })
    const scrollSpy = vi.spyOn(window, "scrollTo").mockImplementation(() => {})
    const { result } = renderHook(() => useNewMessagesIndicator())
    act(() => result.current.notifyNewItem())
    expect(scrollSpy).toHaveBeenCalled()
    expect(result.current.hasNewMessages).toBe(false)
  })

  it("notifyNewItem flags hasNewMessages when scrolled up", () => {
    const { result } = renderHook(() => useNewMessagesIndicator({ initiallyNearBottom: false }))
    act(() => result.current.notifyNewItem())
    expect(result.current.hasNewMessages).toBe(true)
  })

  it("dismiss clears the indicator", () => {
    const { result } = renderHook(() => useNewMessagesIndicator({ initiallyNearBottom: false }))
    act(() => result.current.notifyNewItem())
    expect(result.current.hasNewMessages).toBe(true)
    act(() => result.current.dismiss())
    expect(result.current.hasNewMessages).toBe(false)
  })

  it("scrollToNewMessage scrolls and clears the indicator", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(cb => {
      cb(0)
      return 0
    })
    const scrollSpy = vi.spyOn(window, "scrollTo").mockImplementation(() => {})
    const { result } = renderHook(() => useNewMessagesIndicator({ initiallyNearBottom: false }))
    act(() => result.current.notifyNewItem())
    act(() => result.current.scrollToNewMessage())
    expect(scrollSpy).toHaveBeenCalled()
    expect(result.current.hasNewMessages).toBe(false)
  })

  it("notifyNewItem identity is stable across autoScroll changes", () => {
    const { result, rerender } = renderHook(() => useNewMessagesIndicator())
    const first = result.current.notifyNewItem
    // Simulate a scroll that flips autoScroll by emitting the event and
    // flushing the rAF.
    act(() => {
      window.dispatchEvent(new Event("scroll"))
    })
    rerender()
    expect(result.current.notifyNewItem).toBe(first)
  })
})
