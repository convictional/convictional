import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// Pull-to-refresh installs itself only inside the native shell, so force that on
// to wire up the touch handlers under jsdom. Must be mocked before the module
// under test is imported (install runs at import time).
vi.mock("~/nativeShell", () => ({ isNativeShell: () => true }))

import "~/shared/pullToRefresh"
import { isScrollLocked, lockScroll, unlockScroll } from "~/shared/scrollLock"

// The ring root is the fixed element install() appended; render() stamps this
// transform on it, which no other node carries.
function ring(): HTMLElement {
  const el = [...document.body.children].find(
    node => node instanceof HTMLElement && node.style.transform.includes("translateX(-50%)")
  )
  if (!el) throw new Error("pull-to-refresh ring was not installed")
  return el as HTMLElement
}

function touch(type: string, clientY: number) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.defineProperty(event, "touches", { value: [{ clientY }] })
  document.dispatchEvent(event)
}

beforeEach(() => {
  // The armed "pop" uses the Web Animations API, which jsdom doesn't implement.
  Element.prototype.animate = vi.fn(() => ({}) as Animation) as unknown as Element["animate"]
})

afterEach(() => {
  while (isScrollLocked()) unlockScroll()
  touch("touchcancel", 0) // return the ring to rest between tests
})

describe("pullToRefresh", () => {
  test("does not arm while an overlay holds the scroll lock", () => {
    lockScroll()

    touch("touchstart", 300)
    touch("touchmove", 800) // a strong downward pull that would otherwise arm the ring

    expect(ring().style.opacity).toBe("0") // stays hidden; the open sheet owns the scroll
  })

  test("arms on a top-of-page pull when nothing is locked", () => {
    touch("touchstart", 300)
    touch("touchmove", 800)

    expect(Number(ring().style.opacity)).toBe(1)
  })
})
