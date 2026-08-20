import { describe, expect, test } from "vitest"

import { AXIS_LOCK_RATIO, AXIS_LOCK_SLOP_PX, classifyAxis, rubberBand } from "~/react/shared/swipePhysics"

describe("classifyAxis", () => {
  test("stays undecided until movement clears the slop", () => {
    expect(classifyAxis(0, 0)).toBe("undecided")
    expect(classifyAxis(AXIS_LOCK_SLOP_PX - 1, AXIS_LOCK_SLOP_PX - 1)).toBe("undecided")
    // A dominant-but-tiny delta still waits for the slop before locking.
    expect(classifyAxis(AXIS_LOCK_SLOP_PX - 1, 0)).toBe("undecided")
  })

  test("locks to the axis that dominates once past the slop", () => {
    expect(classifyAxis(40, 0)).toBe("horizontal")
    expect(classifyAxis(0, 40)).toBe("vertical")
  })

  test("requires horizontal to beat vertical by the ratio, else yields to scroll", () => {
    // Just over the ratio → horizontal; just under → vertical (page scrolls).
    expect(classifyAxis(20, 20 / AXIS_LOCK_RATIO - 0.01)).toBe("horizontal")
    expect(classifyAxis(20, 20 / AXIS_LOCK_RATIO + 0.01)).toBe("vertical")
    // A dead-even diagonal is not horizontal-dominant, so it scrolls.
    expect(classifyAxis(20, 20)).toBe("vertical")
  })
})

describe("rubberBand", () => {
  test("tracks 1:1 up to and including the knee", () => {
    expect(rubberBand(0, 80, 0.55)).toBe(0)
    expect(rubberBand(50, 80, 0.55)).toBe(50)
    expect(rubberBand(80, 80, 0.55)).toBe(80)
  })

  test("damps past the knee: monotonic, always beyond the knee but short of 1:1", () => {
    const knee = 80
    const a = rubberBand(120, knee, 0.55)
    const b = rubberBand(240, knee, 0.55)
    expect(a).toBeGreaterThan(knee)
    expect(a).toBeLessThan(120) // resisted, not 1:1
    expect(b).toBeGreaterThan(a) // still increases with pull
    expect(b).toBeLessThan(240)
  })

  test("the shortfall from 1:1 saturates at knee / factor for a huge pull", () => {
    const knee = 104
    const factor = 0.4
    const shortfall = 100_000 - rubberBand(100_000, knee, factor)
    expect(shortfall).toBeLessThan(knee / factor)
    expect(shortfall).toBeGreaterThan(knee / factor - 1) // essentially at the ceiling
  })
})
