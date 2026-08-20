import { act, fireEvent, renderHook } from "@testing-library/react"
import type { MouseEvent as ReactMouseEvent } from "react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { useSwipeReply } from "~/react/shared/hooks/useSwipeReply"

function setup(enabled = true) {
  const onReply = vi.fn()
  const node = document.createElement("div")
  document.body.appendChild(node)
  const view = renderHook(() => useSwipeReply({ enabled, onReply }))
  // The hook binds its (non-passive, native) touch listeners through the
  // callback ref, so attach it to a real node before driving events.
  act(() => view.result.current.ref(node))
  return { ...view, node, onReply }
}

function touches(x: number, y: number) {
  return { touches: [{ clientX: x, clientY: y }] }
}

afterEach(() => {
  document.body.innerHTML = ""
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("useSwipeReply", () => {
  test("a left pull past the trigger arms (with a haptic tick), replies on release, then settles", () => {
    const vibrate = vi.fn()
    vi.stubGlobal("navigator", { ...navigator, vibrate })
    const { result, node, onReply } = setup()

    fireEvent.touchStart(node, touches(200, 100))
    // dx = -90 → pull ≈ 73.8 ≥ trigger. fireEvent returns false when the handler
    // called preventDefault — i.e. the swipe owns the gesture and blocks the
    // page from scrolling vertically mid-pull.
    expect(fireEvent.touchMove(node, touches(110, 100))).toBe(false)

    expect(result.current.swiping).toBe(true)
    expect(result.current.armed).toBe(true)
    expect(result.current.offset).toBeLessThan(0)
    expect(result.current.progress).toBe(1)
    expect(vibrate).toHaveBeenCalledWith(10)

    // Pulling further while still armed must not re-buzz.
    fireEvent.touchMove(node, touches(60, 100))
    expect(vibrate).toHaveBeenCalledOnce()

    fireEvent.touchEnd(node)
    expect(onReply).toHaveBeenCalledOnce()
    expect(result.current.offset).toBe(0)
    expect(result.current.armed).toBe(false)
    expect(result.current.swiping).toBe(false)
  })

  test("a short left pull tracks but never arms, and does not reply on release", () => {
    const { result, node, onReply } = setup()

    fireEvent.touchStart(node, touches(200, 100))
    fireEvent.touchMove(node, touches(160, 100)) // dx = -40 → pull ≈ 32.8 < trigger

    expect(result.current.swiping).toBe(true)
    expect(result.current.armed).toBe(false)
    expect(result.current.offset).toBeLessThan(0)

    fireEvent.touchEnd(node)
    expect(onReply).not.toHaveBeenCalled()
    expect(result.current.offset).toBe(0)
  })

  test("a vertical drag yields to the page scroll: no preventDefault, no offset, even as it turns horizontal", () => {
    const { result, node, onReply } = setup()

    fireEvent.touchStart(node, touches(200, 100))
    // dx = -3, dy = +60 → locks vertical, leaves the touch to scroll the page.
    expect(fireEvent.touchMove(node, touches(197, 160))).toBe(true)
    expect(result.current.swiping).toBe(false)
    expect(result.current.offset).toBe(0)

    // Once the axis is vertical, later horizontal motion stays ignored.
    expect(fireEvent.touchMove(node, touches(120, 200))).toBe(true)
    expect(result.current.offset).toBe(0)

    fireEvent.touchEnd(node)
    expect(onReply).not.toHaveBeenCalled()
  })

  test("a rightward drag rests at zero (reply is left-only)", () => {
    const { result, node } = setup()

    fireEvent.touchStart(node, touches(100, 100))
    fireEvent.touchMove(node, touches(190, 100)) // dx = +90 → horizontal but rightward

    expect(result.current.swiping).toBe(true)
    expect(Math.abs(result.current.offset)).toBe(0)
    expect(result.current.armed).toBe(false)
  })

  test("the rubber band damps a long pull above the cap but well below the raw distance", () => {
    const { result, node } = setup()

    fireEvent.touchStart(node, touches(300, 100))
    fireEvent.touchMove(node, touches(0, 100)) // dx = -300 → raw pull 246

    const offset = Math.abs(result.current.offset)
    // Past MAX_PULL_PX (104) resistance kicks in, so the row can't run away.
    expect(offset).toBeGreaterThan(104)
    expect(offset).toBeLessThan(246)
  })

  test("onClickCapture swallows the synthetic click after a committed swipe, but leaves an ordinary tap alone", () => {
    const { result, node } = setup()

    // No swipe yet: a plain tap's click passes through untouched.
    const tap = { preventDefault: vi.fn(), stopPropagation: vi.fn() } as unknown as ReactMouseEvent
    act(() => result.current.onClickCapture(tap))
    expect(tap.preventDefault).not.toHaveBeenCalled()
    expect(tap.stopPropagation).not.toHaveBeenCalled()

    // Commit a swipe, then the trailing click is suppressed.
    fireEvent.touchStart(node, touches(200, 100))
    fireEvent.touchMove(node, touches(110, 100))
    fireEvent.touchEnd(node)

    const click = { preventDefault: vi.fn(), stopPropagation: vi.fn() } as unknown as ReactMouseEvent
    act(() => result.current.onClickCapture(click))
    expect(click.preventDefault).toHaveBeenCalled()
    expect(click.stopPropagation).toHaveBeenCalled()
  })

  test("binds no listeners while disabled", () => {
    const { result, node, onReply } = setup(false)

    fireEvent.touchStart(node, touches(200, 100))
    fireEvent.touchMove(node, touches(110, 100))
    fireEvent.touchEnd(node)

    expect(result.current.swiping).toBe(false)
    expect(result.current.offset).toBe(0)
    expect(onReply).not.toHaveBeenCalled()
  })
})
