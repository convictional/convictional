import { afterEach, describe, expect, test } from "vitest"

import { isScrollLocked, lockScroll, unlockScroll } from "~/shared/scrollLock"

const html = document.documentElement

// jsdom does no layout (clientWidth is 0), so fake a gutter of innerWidth - clientWidth.
function stubGutter(innerWidth: number, clientWidth: number) {
  Object.defineProperty(window, "innerWidth", { value: innerWidth, configurable: true, writable: true })
  Object.defineProperty(html, "clientWidth", { value: clientWidth, configurable: true })
}

afterEach(() => {
  // Drain any locks a test left so the shared counter can't leak across tests.
  while (isScrollLocked()) unlockScroll()
  html.style.overflow = ""
  html.style.scrollbarGutter = ""
  html.style.paddingRight = ""
  Reflect.deleteProperty(html, "clientWidth")
})

describe("scrollLock", () => {
  test("locks the page, reports the state, and compensates the gutter", () => {
    stubGutter(1000, 985) // 15px reserved gutter
    expect(isScrollLocked()).toBe(false)

    lockScroll()

    expect(isScrollLocked()).toBe(true)
    expect(html.style.overflow).toBe("hidden")
    expect(html.style.scrollbarGutter).toBe("auto")
    expect(html.style.paddingRight).toBe("15px")
  })

  test("restores prior styles and clears the state on release", () => {
    stubGutter(1000, 985)
    lockScroll()
    unlockScroll()

    expect(isScrollLocked()).toBe(false)
    expect(html.style.overflow).toBe("")
    expect(html.style.scrollbarGutter).toBe("")
    expect(html.style.paddingRight).toBe("")
  })

  test("adds no padding when there is no gutter (overlay scrollbars)", () => {
    stubGutter(1000, 1000)
    lockScroll()

    expect(html.style.overflow).toBe("hidden")
    expect(html.style.paddingRight).toBe("")
  })

  test("is ref-counted so stacked locks hold until the last release", () => {
    stubGutter(1000, 985)
    lockScroll()
    lockScroll()

    unlockScroll()
    expect(isScrollLocked()).toBe(true) // second lock still holds it
    expect(html.style.overflow).toBe("hidden")

    unlockScroll()
    expect(isScrollLocked()).toBe(false)
    expect(html.style.overflow).toBe("")
  })

  test("clamps at zero so an extra release can't drive the count negative", () => {
    stubGutter(1000, 985)
    unlockScroll() // release with no lock held

    lockScroll()
    expect(isScrollLocked()).toBe(true) // a single lock still locks, not offset by the underflow
    expect(html.style.overflow).toBe("hidden")
  })
})
