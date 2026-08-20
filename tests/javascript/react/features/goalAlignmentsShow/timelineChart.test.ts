import { describe, expect, test } from "vitest"

import {
  buildLayout,
  buildProgressEvents,
  buildProgressLinePoints,
  buildStatusMarkers,
  interpolateProgress,
} from "~/react/features/goalAlignmentsShow/timelineChart"
import type { TimelineProgressEvent, TimelineStatusChange } from "~/react/features/goalAlignmentsShow/types"

// Fixed 5-week dataset. Two progress updates (weeks 1 and 3), one status change
// (week 3), goal currently at 80% in today's week (4). The expected values below
// are derived from the formulas, not copied from output, so a math change fails.
const progressEvents: TimelineProgressEvent[] = [
  { week_index: 1, progress: 0.2 },
  { week_index: 3, progress: 0.6 },
]
const statusChanges: TimelineStatusChange[] = [{ week_index: 3, status: "at_risk" }]
const CURRENT_PROGRESS = 0.8
const TODAY_WEEK_INDEX = 4
const TOTAL_WEEKS = 5

describe("buildProgressEvents", () => {
  test("anchors at 0% week 0, keeps each event, ends at current progress in today's week", () => {
    expect(buildProgressEvents(progressEvents, CURRENT_PROGRESS, TODAY_WEEK_INDEX)).toEqual([
      { weekIndex: 0, progress: 0 },
      { weekIndex: 1, progress: 0.2 },
      { weekIndex: 3, progress: 0.6 },
      { weekIndex: 4, progress: 0.8 },
    ])
  })
})

describe("interpolateProgress", () => {
  test("holds each event's value (×100) until the next event, leaving no gaps here", () => {
    const points = buildProgressEvents(progressEvents, CURRENT_PROGRESS, TODAY_WEEK_INDEX)
    expect(interpolateProgress(points, TOTAL_WEEKS)).toEqual([0, 20, 20, 60, 80])
  })
})

describe("buildStatusMarkers", () => {
  test("places a marker only where the progress line has a value", () => {
    const progressData = [0, 20, 20, 60, 80]
    expect(buildStatusMarkers(statusChanges, progressData)).toEqual([{ weekIndex: 3, value: 60, status: "at_risk" }])
  })

  test("drops a status change in a week with no interpolated progress", () => {
    const progressData = [0, 20, null, 60, 80]
    expect(buildStatusMarkers([{ week_index: 2, status: "off_track" }], progressData)).toEqual([])
  })
})

describe("buildLayout", () => {
  const layout = buildLayout(500, 200, 3, [0, 20, 20, 60, 80])

  test("divides width evenly into weeks and sizes bars at 70%", () => {
    expect(layout.weekWidth).toBe(100)
    expect(layout.barWidth).toBe(70)
    expect(layout.chartHeight).toBe(180) // 200 - 20px x-axis
    expect(layout.xScale(2)).toBe(200)
    expect(layout.xCenter(2)).toBe(250)
  })

  test("bar scale tops out at 1.5× the busiest week; progress scale is inset by the marker padding", () => {
    // domain [0, 4.5] over range [180, 0]: count 3 → 180 - (3/4.5)*180 = 60
    expect(layout.yBarScale(3)).toBeCloseTo(60)
    expect(layout.yBarScale(0)).toBe(180)
    // domain [0, 100] over range [162, 18] (180 - markerPadding 18 .. 18)
    expect(layout.yProgressScale(0)).toBe(162)
    expect(layout.yProgressScale(100)).toBe(18)
    expect(layout.yProgressScale(60)).toBeCloseTo(75.6)
  })
})

describe("buildProgressLinePoints", () => {
  test("adds a flat hold point before a step when the next event is more than a week away", () => {
    const layout = buildLayout(500, 200, 3, [0, 20, 20, 60, 80])
    const points = buildProgressLinePoints(buildProgressEvents(progressEvents, CURRENT_PROGRESS, TODAY_WEEK_INDEX), layout)
    // week0, week1, hold@week2 (because next event is week3), week3, week4
    expect(points.length).toBe(5)
    expect(points[0][0]).toBe(50) // xCenter(0)
    expect(points[2][0]).toBe(250) // hold at xCenter(2)
    expect(points[2][1]).toBeCloseTo(points[1][1]) // hold keeps the prior value (flat)
    expect(points[4][0]).toBe(450) // xCenter(4)
  })
})
