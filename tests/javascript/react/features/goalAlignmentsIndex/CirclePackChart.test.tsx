import { render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test } from "vitest"

import { CirclePackChart } from "~/react/features/goalAlignmentsIndex/components/CirclePackChart"
import type { GoalGroup, GoalSummary } from "~/react/features/goalAlignmentsIndex/types"

// jsdom does no layout, so clientWidth/clientHeight are 0 (the chart would retry
// forever) and getBBox is unimplemented (the label pill measures text with it).
// Pin a 600×600 viewport so the pack() geometry is deterministic, and stub getBBox
// so the label render doesn't throw.
beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 600 })
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 600 })
  ;(SVGElement.prototype as unknown as { getBBox: () => DOMRect }).getBBox = () =>
    ({ x: 0, y: 0, width: 0, height: 0 }) as DOMRect
})

afterEach(() => {
  delete (HTMLElement.prototype as Partial<HTMLElement>).clientWidth
  delete (HTMLElement.prototype as Partial<HTMLElement>).clientHeight
  delete (SVGElement.prototype as unknown as { getBBox?: unknown }).getBBox
})

function goal(id: string, activity: number): GoalSummary {
  return {
    id,
    name: `Goal ${id}`,
    description: null,
    activity,
    status: "on_track",
    group_id: null,
    group_name: null,
    url: `/goals/${id}/alignments`,
    signal_counts: {},
  }
}

function group(id: string, goals: GoalSummary[]): GoalGroup {
  return { id, name: `Group ${id}`, goals }
}

function nums(els: NodeListOf<Element>, attr: string): number[] {
  return [...els].map(el => Number(el.getAttribute(attr)))
}

describe("CirclePackChart", () => {
  test("draws one outer circle per group and one goal circle per goal", () => {
    const groups = [group("g1", [goal("a", 3), goal("b", 1)])]
    const { container } = render(<CirclePackChart groups={groups} ungroupedGoals={[goal("c", 2)]} />)

    // Two outer circles: the real group plus the synthetic Ungrouped group.
    expect(container.querySelectorAll("circle.outer-circle").length).toBe(2)
    // Three goal circles total (2 grouped + 1 ungrouped).
    expect(container.querySelectorAll("circle.goal-circle").length).toBe(3)
  })

  test("centers a single goal's circle at its group origin with the packed radius", () => {
    // One group, one goal → group radius 200 (busiest, ratio 1). d3.pack centers a
    // lone leaf in the 360×360 box (leaf.x = leaf.y = 180), and the render offsets
    // by -radius*0.9 = -180, so the circle sits at (0, 0) in group coordinates.
    const { container } = render(<CirclePackChart groups={[group("g1", [goal("a", 5)])]} ungroupedGoals={[]} />)

    const circles = container.querySelectorAll("circle.goal-circle")
    expect(circles.length).toBe(1)
    expect(nums(circles, "cx")).toEqual([0])
    expect(nums(circles, "cy")).toEqual([0])
    // Packed radius of a lone leaf in the 360×360 box: ~180 (half the box) minus
    // d3.pack's padding(4) inset. Pinned so a change to the size/padding mapping fails CI.
    expect(circles[0].getAttribute("r")).toBe("176.0869565217391")
  })
})
