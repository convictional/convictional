import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { useZenMode } from "../../../../../app/javascript/react/composites/editor/features/useZenMode"

describe("useZenMode", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    document.documentElement.style.overflow = ""
  })

  test("starts inactive", () => {
    const { result } = renderHook(() => useZenMode())
    expect(result.current.zenMode).toBe(false)
    expect(result.current.exiting).toBe(false)
  })

  test("toggles into zen mode and locks page scroll", () => {
    const { result } = renderHook(() => useZenMode())

    act(() => result.current.toggleZenMode())

    expect(result.current.zenMode).toBe(true)
    expect(result.current.exiting).toBe(false)
    expect(document.documentElement.style.overflow).toBe("hidden")
  })

  test("exit fades out then unmounts", () => {
    const { result } = renderHook(() => useZenMode())

    act(() => result.current.toggleZenMode())
    expect(result.current.zenMode).toBe(true)

    act(() => result.current.toggleZenMode())
    // During exit animation: zenMode stays true (mounted), exiting is true
    expect(result.current.zenMode).toBe(true)
    expect(result.current.exiting).toBe(true)

    act(() => vi.advanceTimersByTime(150))
    // After animation: fully unmounted
    expect(result.current.zenMode).toBe(false)
    expect(result.current.exiting).toBe(false)
    expect(document.documentElement.style.overflow).toBe("")
  })

  test("Escape key exits zen mode", () => {
    const { result } = renderHook(() => useZenMode())

    act(() => result.current.toggleZenMode())
    expect(result.current.zenMode).toBe(true)

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    })
    // Started exiting
    expect(result.current.exiting).toBe(true)

    act(() => vi.advanceTimersByTime(150))
    expect(result.current.zenMode).toBe(false)
  })

  test("rapid toggle cancels exit and re-enters cleanly", () => {
    const { result } = renderHook(() => useZenMode())

    act(() => result.current.toggleZenMode())
    expect(result.current.zenMode).toBe(true)

    // Exit
    act(() => result.current.toggleZenMode())
    expect(result.current.exiting).toBe(true)

    // Re-enter before exit completes
    act(() => result.current.toggleZenMode())
    expect(result.current.zenMode).toBe(true)
    expect(result.current.exiting).toBe(false)

    // Original timer should not unmount
    act(() => vi.advanceTimersByTime(150))
    expect(result.current.zenMode).toBe(true)
  })
})
