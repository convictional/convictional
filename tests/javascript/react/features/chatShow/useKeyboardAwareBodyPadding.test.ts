import { renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { useKeyboardAwareBodyPadding } from "../../../../../app/javascript/react/features/chatShow/ChatShow"

class FakeVisualViewport extends EventTarget {
  height = 800
  offsetTop = 0
}

const INNER_HEIGHT = 800
const ANDROID_UA =
  "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
const IOS_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
let vv: FakeVisualViewport
let scrollToSpy: ReturnType<typeof vi.fn>

function setUserAgent(value: string) {
  Object.defineProperty(window.navigator, "userAgent", { value, configurable: true })
}

function setScrollY(value: number) {
  Object.defineProperty(window, "scrollY", { value, configurable: true, writable: true })
}

function shrinkViewport(toHeight: number) {
  vv.height = toHeight
  vv.dispatchEvent(new Event("resize"))
}

beforeEach(() => {
  // The hook bails on iOS; reset to a non-iOS UA so the iOS test's override
  // doesn't leak into the tests that run after it.
  setUserAgent(ANDROID_UA)
  vv = new FakeVisualViewport()
  Object.defineProperty(window, "visualViewport", { value: vv, configurable: true, writable: true })
  Object.defineProperty(window, "innerHeight", { value: INNER_HEIGHT, configurable: true, writable: true })
  setScrollY(0)
  // Simulate real layout: scrollHeight grows by whatever padding the hook applies.
  // Lets us assert that scrollTo() uses the post-padding height while wasNearBottom
  // is computed against the pre-padding height.
  Object.defineProperty(document.documentElement, "scrollHeight", {
    configurable: true,
    get: () => INNER_HEIGHT + (parseInt(document.body.style.paddingBottom) || 0),
  })
  scrollToSpy = vi.fn()
  window.scrollTo = scrollToSpy as unknown as typeof window.scrollTo
  document.body.style.paddingBottom = ""
})

afterEach(() => {
  document.body.style.paddingBottom = ""
})

describe("useKeyboardAwareBodyPadding", () => {
  test("pads body and scrolls to new bottom when keyboard opens and user was at the bottom", () => {
    renderHook(() => useKeyboardAwareBodyPadding())

    shrinkViewport(500)

    expect(document.body.style.paddingBottom).toBe("300px")
    expect(scrollToSpy).toHaveBeenCalledTimes(1)
    expect(scrollToSpy).toHaveBeenCalledWith({ top: INNER_HEIGHT + 300, behavior: "instant" })
  })

  test("does not scroll when user is not near the bottom", () => {
    // Place user 1000px above bottom by claiming a tall document. The scrollHeight
    // getter reflects padding, so we override it for this case.
    Object.defineProperty(document.documentElement, "scrollHeight", {
      configurable: true,
      get: () => 2000 + (parseInt(document.body.style.paddingBottom) || 0),
    })
    setScrollY(200)

    renderHook(() => useKeyboardAwareBodyPadding())
    shrinkViewport(500)

    expect(document.body.style.paddingBottom).toBe("300px")
    expect(scrollToSpy).not.toHaveBeenCalled()
  })

  test("clears padding when keyboard closes", () => {
    renderHook(() => useKeyboardAwareBodyPadding())

    shrinkViewport(500)
    expect(document.body.style.paddingBottom).toBe("300px")

    shrinkViewport(800)
    expect(document.body.style.paddingBottom).toBe("")
  })

  test("does not pad on iOS, whose layout viewport already shrinks with the keyboard", () => {
    setUserAgent(IOS_UA)
    renderHook(() => useKeyboardAwareBodyPadding())

    shrinkViewport(500)

    expect(document.body.style.paddingBottom).toBe("")
    expect(scrollToSpy).not.toHaveBeenCalled()
  })

  test("cleanup clears padding and detaches listeners", () => {
    const { unmount } = renderHook(() => useKeyboardAwareBodyPadding())

    shrinkViewport(500)
    expect(document.body.style.paddingBottom).toBe("300px")

    unmount()
    expect(document.body.style.paddingBottom).toBe("")

    scrollToSpy.mockClear()
    shrinkViewport(400)
    expect(document.body.style.paddingBottom).toBe("")
    expect(scrollToSpy).not.toHaveBeenCalled()
  })
})
