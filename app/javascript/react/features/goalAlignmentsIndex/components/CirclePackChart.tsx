import { useCallback, useEffect, useRef, useState } from "react"

import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { renderCirclePack, type CirclePosition } from "../circlePackChart"
import type { GoalGroup, GoalSummary } from "../types"
import { GoalTooltip } from "./GoalTooltip"

// React owns the container <div>/ref and the hover tooltip state; the D3 render
// runs imperatively against the container in an effect (see circlePackChart.ts).
// Renders once — re-running the layout on resize is a deliberate follow-up.
export function CirclePackChart({ groups, ungroupedGoals }: { groups: GoalGroup[]; ungroupedGoals: GoalSummary[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const hideTimerRef = useRef<number | null>(null)
  const [activeGoal, setActiveGoal] = useState<GoalSummary | null>(null)
  const [tooltipPosition, setTooltipPosition] = useState({ left: 0, top: 0 })

  const cancelHideTooltip = useCallback(() => {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current)
      hideTimerRef.current = null
    }
  }, [])

  const hideTooltip = useCallback(() => {
    setActiveGoal(null)
    hideTimerRef.current = null
  }, [])

  // Hide on a short delay so moving the cursor from a circle onto the tooltip
  // (which sits a small gap below) doesn't flicker it closed.
  const scheduleHideTooltip = useCallback(() => {
    cancelHideTooltip()
    hideTimerRef.current = window.setTimeout(hideTooltip, 150)
  }, [cancelHideTooltip, hideTooltip])

  // Positions the tooltip below the hovered circle, clamped into the viewport and
  // flipped above the circle if it would overflow the bottom. The height is an
  // estimate (GoalTooltip is content-driven, no fixed height); it only drives the
  // flip decision, not layout, so a generous value covering a two-line description
  // is enough without measuring.
  const showTooltip = useCallback(
    (goal: GoalSummary, circlePos: CirclePosition, containerRect: DOMRect) => {
      cancelHideTooltip()
      setActiveGoal(goal)

      const tooltipWidth = 320
      const tooltipHeight = 160
      const gap = 8

      const circleScreenX = containerRect.left + circlePos.cx
      const circleScreenY = containerRect.top + circlePos.cy
      const circleBottom = circleScreenY + circlePos.r

      let x = circleScreenX - tooltipWidth / 2
      let y = circleBottom + gap

      if (x < 8) {
        x = 8
      } else if (x + tooltipWidth > window.innerWidth - 8) {
        x = window.innerWidth - tooltipWidth - 8
      }

      if (y + tooltipHeight > window.innerHeight - 8) {
        y = circleScreenY - circlePos.r - tooltipHeight - gap
      }

      setTooltipPosition({ left: x, top: y })
    },
    [cancelHideTooltip]
  )

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    let cleanup = () => {}
    let cancelled = false
    let attempts = 0

    // The container may have no layout yet on mount; retry on the next frame
    // (up to ~60 frames) until it has a non-zero size.
    const render = () => {
      if (cancelled) return
      const width = container.clientWidth
      const height = container.clientHeight
      if (width === 0 || height === 0) {
        if (++attempts < 60) requestAnimationFrame(render)
        return
      }
      cleanup = renderCirclePack(container, groups, ungroupedGoals, width, height, {
        onGoalEnter: showTooltip,
        onGoalLeave: scheduleHideTooltip,
      })
    }

    render()

    return () => {
      cancelled = true
      cleanup()
      cancelHideTooltip()
    }
  }, [groups, ungroupedGoals, showTooltip, scheduleHideTooltip, cancelHideTooltip])

  // The tooltip's "open" anchor mounts on hover (activeGoal), after the island
  // root's boost pass, so boost this subtree whenever the tooltip toggles.
  useBoostIslandLinks(rootRef, [activeGoal])

  return (
    <div ref={rootRef} className="px-2 mb-6">
      <div className="rounded-xl overflow-hidden bg-[radial-gradient(circle,var(--color-base-400)_1px,transparent_1px)] bg-size-[12px_12px]">
        <div ref={containerRef} className="h-112 w-full" />
        {activeGoal && (
          <GoalTooltip
            goal={activeGoal}
            position={tooltipPosition}
            onMouseEnter={cancelHideTooltip}
            onMouseLeave={scheduleHideTooltip}
          />
        )}
      </div>
    </div>
  )
}
