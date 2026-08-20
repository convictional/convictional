import { useEffect, useRef } from "react"

import { renderTimelineChart } from "../timelineChart"
import type { AlignmentTimelineData } from "../types"

// Thin React shell: React owns the container <div> and its lifecycle, while the
// D3 render (scales, bucketing, SVG construction, hover tooltips) runs
// imperatively against the container in an effect, rather than re-deriving the
// chart math as declarative JSX. A ResizeObserver re-renders on width changes so
// the chart stays responsive.
export function AlignmentTimelineChart({ timeline }: { timeline: AlignmentTimelineData }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const render = () => {
      const width = container.clientWidth
      const height = container.clientHeight
      if (width > 0 && height > 0) renderTimelineChart(container, timeline, width, height)
    }

    render()

    const observer = new ResizeObserver(render)
    observer.observe(container)
    return () => observer.disconnect()
  }, [timeline])

  return (
    <div className="mb-6">
      <div className="rounded-xl card bg-base-50 border border-base-300 overflow-hidden">
        <div ref={containerRef} className="h-64 w-full" />
      </div>
    </div>
  )
}
