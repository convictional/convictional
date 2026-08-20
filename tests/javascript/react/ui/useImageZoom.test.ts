import { act, renderHook } from "@testing-library/react"
import type { RefObject } from "react"
import { describe, expect, test } from "vitest"

import { useImageZoom } from "~/react/ui/hooks/useImageZoom"

function refTo(width = 200, height = 200): RefObject<HTMLElement> {
  const el = document.createElement("div")
  Object.defineProperty(el, "clientWidth", { value: width })
  Object.defineProperty(el, "clientHeight", { value: height })
  return { current: el }
}

describe("useImageZoom", () => {
  test("starts unzoomed and clamps scale to [1, 5]", () => {
    const { result } = renderHook(() => useImageZoom(refTo()))
    expect(result.current.scale).toBe(1)
    expect(result.current.isZoomed).toBe(false)

    act(() => result.current.setScale(99))
    expect(result.current.scale).toBe(5)

    act(() => result.current.setScale(0.1))
    expect(result.current.scale).toBe(1)
  })

  test("zoomIn/zoomOut step and reset returns to fit", () => {
    const { result } = renderHook(() => useImageZoom(refTo()))
    act(() => result.current.zoomIn())
    expect(result.current.scale).toBe(1.5)
    act(() => result.current.zoomIn())
    expect(result.current.scale).toBe(2)
    act(() => result.current.zoomOut())
    expect(result.current.scale).toBe(1.5)

    act(() => result.current.reset())
    expect(result.current.scale).toBe(1)
    expect(result.current.isZoomed).toBe(false)
  })

  test("toggle flips between fit and 2x", () => {
    const { result } = renderHook(() => useImageZoom(refTo()))
    act(() => result.current.toggle())
    expect(result.current.scale).toBe(2)
    act(() => result.current.toggle())
    expect(result.current.scale).toBe(1)
  })

  test("pan is clamped to the zoomed overflow and reset to 0 when unzoomed", () => {
    const { result } = renderHook(() => useImageZoom(refTo(200, 200)))
    act(() => result.current.setScale(2))
    // Max pan at scale 2 over a 200px image is (2-1)*200/2 = 100px each way.
    act(() => result.current.panBy(500, -500))
    expect(result.current.offset).toEqual({ x: 100, y: -100 })

    // Returning to fit recenters.
    act(() => result.current.setScale(1))
    expect(result.current.offset).toEqual({ x: 0, y: 0 })
  })
})
