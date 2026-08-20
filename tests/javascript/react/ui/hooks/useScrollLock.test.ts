import { renderHook } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { useScrollLock } from "~/react/ui/hooks/useScrollLock"

const html = document.documentElement

// jsdom does no layout (clientWidth is 0), so fake a gutter of innerWidth - clientWidth.
function stubGutter(innerWidth: number, clientWidth: number) {
  Object.defineProperty(window, "innerWidth", { value: innerWidth, configurable: true, writable: true })
  Object.defineProperty(html, "clientWidth", { value: clientWidth, configurable: true })
}

afterEach(() => {
  html.style.overflow = ""
  html.style.scrollbarGutter = ""
  html.style.paddingRight = ""
  Reflect.deleteProperty(html, "clientWidth")
})

describe("useScrollLock", () => {
  test("collapses the reserved gutter and compensates with padding on lock", () => {
    stubGutter(1000, 985) // 15px reserved gutter
    const { unmount } = renderHook(() => useScrollLock())

    expect(html.style.overflow).toBe("hidden")
    expect(html.style.scrollbarGutter).toBe("auto")
    expect(html.style.paddingRight).toBe("15px")

    unmount()
  })

  test("restores the prior styles when the last lock releases", () => {
    stubGutter(1000, 985)
    const { unmount } = renderHook(() => useScrollLock())
    unmount()

    expect(html.style.overflow).toBe("")
    expect(html.style.scrollbarGutter).toBe("")
    expect(html.style.paddingRight).toBe("")
  })

  test("adds no padding when there is no gutter (overlay scrollbars)", () => {
    stubGutter(1000, 1000) // no reserved gutter
    const { unmount } = renderHook(() => useScrollLock())

    expect(html.style.overflow).toBe("hidden")
    expect(html.style.paddingRight).toBe("")

    unmount()
  })

  test("is ref-counted so stacked overlays don't unlock the page early", () => {
    stubGutter(1000, 985)
    const first = renderHook(() => useScrollLock())
    const second = renderHook(() => useScrollLock())
    expect(html.style.overflow).toBe("hidden")

    first.unmount()
    expect(html.style.overflow).toBe("hidden") // second lock still holds it

    second.unmount()
    expect(html.style.overflow).toBe("")
  })

  test("releases when enabled flips to false without unmounting", () => {
    // How Dialog uses it: useScrollLock(isOpen) where isOpen toggles in place.
    stubGutter(1000, 985)
    const { rerender } = renderHook(({ enabled }) => useScrollLock(enabled), { initialProps: { enabled: true } })
    expect(html.style.overflow).toBe("hidden")

    rerender({ enabled: false })
    expect(html.style.overflow).toBe("")
  })

  test("does nothing while disabled", () => {
    stubGutter(1000, 985)
    const { unmount } = renderHook(({ enabled }) => useScrollLock(enabled), { initialProps: { enabled: false } })

    expect(html.style.overflow).toBe("")
    expect(html.style.paddingRight).toBe("")

    unmount()
  })
})
