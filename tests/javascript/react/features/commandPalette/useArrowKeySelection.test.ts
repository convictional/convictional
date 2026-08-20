import { renderHook } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"

import { useArrowKeySelection } from "../../../../../app/javascript/react/features/commandPalette/useArrowKeySelection"

function buildOpts(overrides: Partial<Parameters<typeof useArrowKeySelection>[0]> = {}) {
  return {
    itemCount: 3,
    selectedIndex: 0,
    setSelectedIndex: vi.fn(),
    onActivate: vi.fn(),
    mouseEnabled: false,
    setMouseEnabled: vi.fn(),
    initialMouse: null,
    setInitialMouse: vi.fn(),
    ...overrides,
  }
}

describe("useArrowKeySelection", () => {
  test("arrow down wraps modulo count", () => {
    const opts = buildOpts({ selectedIndex: 2 })
    const { result } = renderHook(() => useArrowKeySelection(opts))
    result.current.handleArrowDown()
    expect(opts.setSelectedIndex).toHaveBeenCalledWith(0)
  })

  test("arrow up wraps to last item", () => {
    const opts = buildOpts({ selectedIndex: 0 })
    const { result } = renderHook(() => useArrowKeySelection(opts))
    result.current.handleArrowUp()
    expect(opts.setSelectedIndex).toHaveBeenCalledWith(2)
  })

  test("arrow keys disable mouse hover (gate reset)", () => {
    const opts = buildOpts({ mouseEnabled: true })
    const { result } = renderHook(() => useArrowKeySelection(opts))
    result.current.handleArrowDown()
    expect(opts.setMouseEnabled).toHaveBeenCalledWith(false)
  })

  test("enter activates current index", () => {
    const opts = buildOpts({ selectedIndex: 1 })
    const { result } = renderHook(() => useArrowKeySelection(opts))
    result.current.handleEnter()
    expect(opts.onActivate).toHaveBeenCalledWith(1)
  })

  test("mouse gate: first move records baseline, no activation", () => {
    const opts = buildOpts({ initialMouse: null })
    const { result } = renderHook(() => useArrowKeySelection(opts))
    result.current.handleMouseMove({ clientX: 10, clientY: 10 })
    expect(opts.setInitialMouse).toHaveBeenCalledWith({ x: 10, y: 10 })
    expect(opts.setMouseEnabled).not.toHaveBeenCalled()
  })

  test("mouse gate: <10px movement keeps mouse disabled", () => {
    const opts = buildOpts({ initialMouse: { x: 10, y: 10 } })
    const { result } = renderHook(() => useArrowKeySelection(opts))
    result.current.handleMouseMove({ clientX: 13, clientY: 13 })
    expect(opts.setMouseEnabled).not.toHaveBeenCalled()
  })

  test("mouse gate: >10px movement enables mouse", () => {
    const opts = buildOpts({ initialMouse: { x: 10, y: 10 } })
    const { result } = renderHook(() => useArrowKeySelection(opts))
    result.current.handleMouseMove({ clientX: 30, clientY: 30 })
    expect(opts.setMouseEnabled).toHaveBeenCalledWith(true)
  })

  test("handleItemHover is a no-op when mouse disabled", () => {
    const opts = buildOpts({ mouseEnabled: false })
    const { result } = renderHook(() => useArrowKeySelection(opts))
    result.current.handleItemHover(2)
    expect(opts.setSelectedIndex).not.toHaveBeenCalled()
  })
})
