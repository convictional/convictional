import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { withScrollPreserved } from "../../../../../app/javascript/react/composites/reactions/scrollUtils"

let scrollY: number
let scrollToSpy: ReturnType<typeof vi.fn>
let rafCallbacks: FrameRequestCallback[]
let originalRAF: typeof window.requestAnimationFrame

function setScrollY(value: number) {
  scrollY = value
  Object.defineProperty(window, "scrollY", { configurable: true, get: () => scrollY })
}

function flushRAF() {
  const cbs = rafCallbacks
  rafCallbacks = []
  cbs.forEach(cb => cb(performance.now()))
}

beforeEach(() => {
  setScrollY(500)
  scrollToSpy = vi.fn((opts?: ScrollToOptions | number) => {
    if (typeof opts === "object" && opts && typeof opts.top === "number") scrollY = opts.top
  })
  window.scrollTo = scrollToSpy as unknown as typeof window.scrollTo
  rafCallbacks = []
  originalRAF = window.requestAnimationFrame
  window.requestAnimationFrame = ((cb: FrameRequestCallback) => {
    rafCallbacks.push(cb)
    return rafCallbacks.length
  }) as typeof window.requestAnimationFrame
})

afterEach(() => {
  window.requestAnimationFrame = originalRAF
})

describe("withScrollPreserved", () => {
  test("restores scrollY on next frame when the action moves it", () => {
    withScrollPreserved(() => {
      // Simulate WebKit's scroll-anchor heuristic: scrollY changes during the
      // action's downstream effects (e.g. an optimistic re-render).
      setScrollY(80)
    })

    // Before the rAF fires, the moved scrollY is still in place — the helper
    // doesn't fight WebKit synchronously, it lets the move happen and undoes it.
    expect(scrollY).toBe(80)
    expect(scrollToSpy).not.toHaveBeenCalled()

    flushRAF()

    expect(scrollToSpy).toHaveBeenCalledWith({ top: 500, behavior: "instant" })
  })

  test("does not call scrollTo when the action leaves scrollY unchanged", () => {
    withScrollPreserved(() => {
      // The action doesn't move scroll (this is the non-Safari case).
    })

    flushRAF()

    expect(scrollToSpy).not.toHaveBeenCalled()
  })

  test("snapshots scrollY synchronously before the action runs", () => {
    // If the snapshot were deferred (e.g. read inside the rAF), it would capture
    // the post-mutation value and the restore would be a no-op against the wrong
    // baseline. Mutating scrollY before flushing rAF proves the snapshot was
    // taken at call time.
    withScrollPreserved(() => {
      setScrollY(80)
    })
    setScrollY(120)

    flushRAF()

    expect(scrollToSpy).toHaveBeenCalledWith({ top: 500, behavior: "instant" })
  })
})
