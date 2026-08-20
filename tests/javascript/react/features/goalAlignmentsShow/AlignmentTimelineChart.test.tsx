import { render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test } from "vitest"

import { AlignmentTimelineChart } from "~/react/features/goalAlignmentsShow/components/AlignmentTimelineChart"
import type { AlignmentTimelineData } from "~/react/features/goalAlignmentsShow/types"

// jsdom does no layout, so clientWidth/clientHeight are 0 and the chart would
// no-op. Pin them to a fixed 500×200 viewport so the rendered SVG geometry is
// deterministic and the assertions below can pin exact pixel coordinates.
beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 500 })
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 200 })
})

afterEach(() => {
  delete (HTMLElement.prototype as Partial<HTMLElement>).clientWidth
  delete (HTMLElement.prototype as Partial<HTMLElement>).clientHeight
})

const timeline: AlignmentTimelineData = {
  weekly_activity: [
    { week: "2026-01-05", count: 0 },
    { week: "2026-01-12", count: 3 },
    { week: "2026-01-19", count: 1 },
    { week: "2026-01-26", count: 0 },
    { week: "2026-02-02", count: 2 },
  ],
  progress_events: [
    { week_index: 1, progress: 0.2 },
    { week_index: 3, progress: 0.6 },
  ],
  status_changes: [{ week_index: 3, status: "at_risk" }],
  current_progress: 0.8,
  current_status: "at_risk",
  total_weeks: 5,
  today_week_index: 4,
  start_date: "2026-01-05",
  end_date: "2026-02-02",
}

function nums(els: NodeListOf<Element>, attr: string): number[] {
  return [...els].map(el => Number(el.getAttribute(attr)))
}

describe("AlignmentTimelineChart", () => {
  test("renders one bar per active week at the computed x/width", () => {
    const { container } = render(<AlignmentTimelineChart timeline={timeline} />)
    const bars = container.querySelectorAll("rect.activity-bar")
    // Weeks 0 and 3 have count 0, so only 3 bars are drawn.
    expect(bars.length).toBe(3)
    // barWidth = 70; x = xCenter(weekIndex) - 35 for weeks 1, 2, 4.
    expect(nums(bars, "x")).toEqual([115, 215, 415])
    expect(nums(bars, "width")).toEqual([70, 70, 70])
  })

  test("renders a label per week, progress dots off the status weeks, and one status marker", () => {
    const { container } = render(<AlignmentTimelineChart timeline={timeline} />)

    expect(container.querySelectorAll("text.week-label").length).toBe(5)

    // Event weeks are 0, 1, 3, 4; week 3 is shown as a status marker, so dots
    // are drawn at weeks 0, 1, 4 → cx 50, 150, 450.
    const dots = container.querySelectorAll("circle.progress-dot")
    expect(nums(dots, "cx")).toEqual([50, 150, 450])

    const markers = container.querySelectorAll("g.status-marker")
    expect(markers.length).toBe(1)
    // translate(xCenter(3)=350, yProgressScale(60)=75.6)
    expect(markers[0].getAttribute("transform")).toBe("translate(350, 75.6)")
  })

  test("draws no today divider when today is the last week", () => {
    const { container } = render(<AlignmentTimelineChart timeline={timeline} />)
    expect(container.querySelectorAll("line").length).toBe(0)
  })

  test("renders nothing for an empty timeline", () => {
    const empty: AlignmentTimelineData = { ...timeline, total_weeks: 0 }
    const { container } = render(<AlignmentTimelineChart timeline={empty} />)
    expect(container.querySelector("svg")).toBeNull()
  })
})
