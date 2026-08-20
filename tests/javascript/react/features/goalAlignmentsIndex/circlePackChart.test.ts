import { describe, expect, test } from "vitest"

import { buildAllGroups, buildGroupNodes } from "~/react/features/goalAlignmentsIndex/circlePackChart"
import type { GoalGroup, GoalSummary } from "~/react/features/goalAlignmentsIndex/types"

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

describe("buildAllGroups", () => {
  test("appends a synthetic Ungrouped group when there are ungrouped goals", () => {
    const groups = [group("g1", [goal("a", 1)])]
    const all = buildAllGroups(groups, [goal("b", 2)])

    expect(all).toHaveLength(2)
    expect(all[1]).toMatchObject({ id: "ungrouped", name: "Ungrouped" })
    expect(all[1].goals.map(g => g.id)).toEqual(["b"])
  })

  test("returns only the real groups when there are no ungrouped goals", () => {
    const groups = [group("g1", [goal("a", 1)])]
    expect(buildAllGroups(groups, [])).toHaveLength(1)
  })
})

describe("buildGroupNodes", () => {
  // At 600×600: minRadius=40, maxRadius=min(w,h)/3=200, spreadRadius=min(w,h)/4=150.
  // Group activity is the sum of its goals' activity; the radius scales linearly
  // from minRadius (ratio 0) to maxRadius (ratio 1, the busiest group).
  test("scales each group's radius by its activity ratio and seeds positions on a ring", () => {
    const groups = [
      group("g1", [goal("a", 6), goal("b", 4)]), // total 10 (busiest → ratio 1)
      group("g2", [goal("c", 5)]), //               total 5  (ratio 0.5)
    ]

    const nodes = buildGroupNodes(groups, 600, 600)

    // ratio 1 → 40 + (200-40)*1 = 200; ratio 0.5 → 40 + 160*0.5 = 120.
    expect(nodes.map(n => n.radius)).toEqual([200, 120])

    // angle i: 0 and π. x = 300 + cos(angle)*150, y = 300 + sin(angle)*150.
    expect(nodes[0].x).toBeCloseTo(450)
    expect(nodes[0].y).toBeCloseTo(300)
    expect(nodes[1].x).toBeCloseTo(150)
    expect(nodes[1].y).toBeCloseTo(300)
  })

  test("gives a zero-activity group the minimum radius", () => {
    const groups = [group("g1", [goal("a", 0)])]
    // maxGroupActivity floors at 1, so ratio 0 → radius == minRadius.
    expect(buildGroupNodes(groups, 600, 600)[0].radius).toBe(40)
  })
})
