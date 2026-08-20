import * as d3 from "d3"

import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { STATUS_OPTIONS } from "~/react/shared/statusConfig"
import type { GoalGroup, GoalSummary } from "./types"

// Owns the D3 math (group force layout + per-group circle packing) and SVG
// construction, run imperatively against a container React provides. The pure
// layout helpers (buildAllGroups, buildGroupNodes) are exported so the geometry
// can be unit-tested against fixed data.

export interface CirclePosition {
  cx: number
  cy: number
  r: number
}

interface GroupNode {
  id: string
  name: string
  goals: GoalSummary[]
  radius: number
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

interface BadgeStyles {
  bgColor: string
  borderColor: string
  textColor: string
  fontSize: string
  fontWeight: string
  borderRadius: string
  boxShadow: string
}

interface CirclePackCallbacks {
  onGoalEnter(goal: GoalSummary, circlePos: CirclePosition, containerRect: DOMRect): void
  onGoalLeave(): void
}

const STATUS_ICONS: Record<string, string> = {
  on_track: "check",
  at_risk: "warning",
  off_track: "close",
}

// Colors come from the daisyUI theme, which only exists as resolved CSS on a
// mounted element, so we read them off a throwaway hidden node rather than
// hardcoding hex values that would drift from the theme.
function extractComputedStyles(
  elementClass: string,
  properties: (keyof CSSStyleDeclaration)[]
): Record<string, string> {
  const el = document.createElement("div")
  el.className = elementClass
  el.style.position = "absolute"
  el.style.visibility = "hidden"
  document.body.appendChild(el)
  const computed = getComputedStyle(el)
  const result = Object.fromEntries(properties.map(p => [p, computed[p] as string]))
  document.body.removeChild(el)
  return result
}

function extractBadgeStyles(): BadgeStyles {
  const badgeEl = document.createElement("div")
  badgeEl.className = "dropdown-card rounded-lg shadow-sm"
  badgeEl.style.position = "absolute"
  badgeEl.style.visibility = "hidden"

  const badgeTextEl = document.createElement("span")
  badgeTextEl.className = "text-xs text-base-600/70 font-semibold"
  badgeEl.appendChild(badgeTextEl)
  document.body.appendChild(badgeEl)

  const badgeStyles = getComputedStyle(badgeEl)
  const badgeTextStyles = getComputedStyle(badgeTextEl)
  const result: BadgeStyles = {
    bgColor: badgeStyles.backgroundColor,
    borderColor: badgeStyles.borderColor,
    textColor: badgeTextStyles.color,
    fontSize: badgeTextStyles.fontSize,
    fontWeight: badgeTextStyles.fontWeight,
    borderRadius: badgeStyles.borderRadius,
    boxShadow: badgeStyles.boxShadow,
  }

  document.body.removeChild(badgeEl)
  return result
}

function extractStatusBorderColors(): Record<string, string> {
  return Object.fromEntries(
    STATUS_OPTIONS.map(({ value, textClass }) => [value, extractComputedStyles(textClass, ["color"]).color])
  )
}

// Appends the synthetic "Ungrouped" group so ungrouped goals get their own packed
// bubble alongside the real groups. Pure (no DOM) so it can be unit-tested.
export function buildAllGroups(groups: GoalGroup[], ungroupedGoals: GoalSummary[]): GoalGroup[] {
  const allGroups = [...groups]
  if (ungroupedGoals.length > 0) {
    allGroups.push({ id: "ungrouped", name: "Ungrouped", goals: ungroupedGoals })
  }
  return allGroups
}

// Each group's outer-circle radius scales with its total alignment activity
// (linearly between minRadius and maxRadius, relative to the busiest group), and
// the groups are seeded evenly around a ring so the force layout starts spread
// out rather than stacked. Pure (no DOM) so the radius/activity math can be tested.
export function buildGroupNodes(allGroups: GoalGroup[], width: number, height: number): GroupNode[] {
  const minRadius = 40
  const maxRadius = Math.min(width, height) / 3

  const groupActivities = allGroups.map(g => g.goals.reduce((sum, goal) => sum + goal.activity, 0))
  const maxGroupActivity = Math.max(...groupActivities, 1)
  const spreadRadius = Math.min(width, height) / 4

  return allGroups.map((group, i) => {
    const activityRatio = groupActivities[i] / maxGroupActivity
    const radius = minRadius + (maxRadius - minRadius) * activityRatio
    const angle = (2 * Math.PI * i) / allGroups.length
    return {
      id: group.id,
      name: group.name,
      goals: group.goals,
      radius,
      x: width / 2 + Math.cos(angle) * spreadRadius,
      y: height / 2 + Math.sin(angle) * spreadRadius,
    }
  })
}

function createSvgWithDefs(
  container: HTMLElement,
  width: number,
  height: number
): d3.Selection<SVGSVGElement, unknown, null, undefined> {
  const svg = d3
    .select(container)
    .append("svg")
    .attr("width", "100%")
    .attr("height", "100%")
    .attr("viewBox", `0 0 ${width} ${height}`)

  const highlightGradient = svg
    .append("defs")
    .append("linearGradient")
    .attr("id", "badge-inset-highlight")
    .attr("x1", "0%")
    .attr("y1", "0%")
    .attr("x2", "0%")
    .attr("y2", "100%")

  highlightGradient.append("stop").attr("offset", "0%").attr("stop-color", "white").attr("stop-opacity", "0.15")
  highlightGradient.append("stop").attr("offset", "50%").attr("stop-color", "white").attr("stop-opacity", "0")

  return svg
}

// The group label is a pill behind centered text. The rect is inserted after
// measuring the text bbox (so it hugs the label), then a second rect overlays the
// inset-highlight gradient. Drawn in two insert("rect", "text") calls so both
// rects sit behind the text in document order.
function renderGroupBadgeLabel(
  labelGroup: d3.Selection<SVGGElement, GroupNode, SVGSVGElement, unknown>,
  badge: BadgeStyles
): void {
  const borderRadiusPx = parseFloat(badge.borderRadius) || 6

  labelGroup.each(function (d) {
    const g = d3.select(this)

    const text = g
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .style("fill", badge.textColor)
      .style("font-size", badge.fontSize)
      .style("font-weight", badge.fontWeight)
      .text(d.name)

    const bbox = (text.node() as SVGTextElement).getBBox()
    const paddingX = 8
    const paddingY = 4
    const rectX = bbox.x - paddingX
    const rectY = bbox.y - paddingY
    const rectW = bbox.width + paddingX * 2
    const rectH = bbox.height + paddingY * 2

    g.insert("rect", "text")
      .attr("x", rectX)
      .attr("y", rectY)
      .attr("width", rectW)
      .attr("height", rectH)
      .attr("rx", borderRadiusPx)
      .attr("ry", borderRadiusPx)
      .style("fill", badge.bgColor)
      .style("stroke", badge.borderColor)
      .style("stroke-width", "1px")
      .style("filter", badge.boxShadow !== "none" ? `drop-shadow(0 1px 2px rgb(0 0 0 / 0.05))` : "")

    g.insert("rect", "text")
      .attr("x", rectX)
      .attr("y", rectY)
      .attr("width", rectW)
      .attr("height", rectH)
      .attr("rx", borderRadiusPx)
      .attr("ry", borderRadiusPx)
      .style("fill", "url(#badge-inset-highlight)")
      .style("pointer-events", "none")
  })
}

// Packs each group's goals into its outer circle with d3.pack(). The pack box is
// 1.8× the group radius and the leaf coordinates are recentered onto the group
// origin (subtracting radius * 0.9) so the packed cluster sits centered in the
// outer circle. Circle area encodes activity (value = max(activity, 1) so a
// zero-activity goal still gets a visible dot); status drives the fill/icon.
function renderGoalCircles(
  groupContainers: d3.Selection<SVGGElement, GroupNode, SVGSVGElement, unknown>,
  statusBorderColors: Record<string, string>,
  container: HTMLElement,
  onEnter: (goal: GoalSummary, circlePos: CirclePosition, containerRect: DOMRect) => void,
  onLeave: () => void
): void {
  groupContainers.each(function (groupNode) {
    const group = d3.select(this)
    const goals = groupNode.goals
    if (goals.length === 0) return

    const hierarchyData = {
      children: goals.map(goal => ({ ...goal, value: Math.max(goal.activity, 1) })),
    }

    const packed = d3
      .pack<typeof hierarchyData>()
      .size([groupNode.radius * 1.8, groupNode.radius * 1.8])
      .padding(4)(d3.hierarchy(hierarchyData).sum(d => (d as { value?: number }).value || 0))

    packed.leaves().forEach(leaf => {
      const goal = leaf.data as unknown as GoalSummary & { value: number }
      const cx = leaf.x - groupNode.radius * 0.9
      const cy = leaf.y - groupNode.radius * 0.9
      const goalRadius = leaf.r

      const status = goal.status || "on_track"
      const strokeColor = statusBorderColors[status] || statusBorderColors.on_track
      const icon = STATUS_ICONS[status] || STATUS_ICONS.on_track

      const goalCircle = group
        .append("circle")
        .attr("class", "goal-circle")
        .attr("cx", cx)
        .attr("cy", cy)
        .attr("r", goalRadius)
        .attr("fill", strokeColor)
        .style("fill-opacity", 0.25)
        .attr("stroke", strokeColor)
        .attr("stroke-width", 1)
        .style("stroke-opacity", 0.5)
        .style("cursor", "pointer")

      const iconEl = group
        .append("text")
        .attr("class", "material-symbols-outlined")
        .attr("x", cx)
        .attr("y", cy)
        .attr("text-anchor", "middle")
        .attr("dominant-baseline", "central")
        .style("font-size", "18px")
        .style("fill", strokeColor)
        .style("pointer-events", "none")
        .text(icon)

      goalCircle
        .on("mouseenter", function () {
          d3.select(this).style("fill-opacity", 0.5)
          iconEl.style("fill", "white")
          // The circle sits inside the group <g>, so its absolute position is the
          // group's simulated origin plus the leaf offset.
          const circlePos: CirclePosition = {
            cx: (groupNode.x || 0) + cx,
            cy: (groupNode.y || 0) + cy,
            r: goalRadius,
          }
          onEnter(goal, circlePos, container.getBoundingClientRect())
        })
        .on("mouseleave", function () {
          d3.select(this).style("fill-opacity", 0.25)
          iconEl.style("fill", strokeColor)
          onLeave()
        })
        .on("click", () => {
          boostedNavigate(goal.url)
        })
    })
  })
}

function createDragBehavior(
  simulation: d3.Simulation<GroupNode, undefined>
): d3.DragBehavior<SVGGElement, GroupNode, GroupNode | d3.SubjectPosition> {
  return d3
    .drag<SVGGElement, GroupNode>()
    .on("start", function (_event, d) {
      d3.select(this).style("cursor", "grabbing")
      simulation.alphaTarget(0.3).restart()
      d.fx = d.x
      d.fy = d.y
    })
    .on("drag", function (event, d) {
      d.fx = event.x
      d.fy = event.y
    })
    .on("end", function (_event, d) {
      d3.select(this).style("cursor", "grab")
      simulation.alphaTarget(0)
      d.fx = null
      d.fy = null
    })
}

// Renders the circle-pack into `container` at the given pixel size and returns a
// cleanup that stops the force simulation. Clears any prior render first so it's
// safe to call again. Assumes a non-empty overview: the React island renders an
// EmptyState instead of mounting this when there are no goals.
export function renderCirclePack(
  container: HTMLElement,
  groups: GoalGroup[],
  ungroupedGoals: GoalSummary[],
  width: number,
  height: number,
  callbacks: CirclePackCallbacks
): () => void {
  container.innerHTML = ""

  const allGroups = buildAllGroups(groups, ungroupedGoals)
  if (allGroups.length === 0) return () => {}

  const { backgroundColor: circleColor, borderColor: circleBorderColor } = extractComputedStyles(
    "bg-base-50 border-neutral text-base-content",
    ["backgroundColor", "borderColor"]
  )
  const badgeStyles = extractBadgeStyles()
  const statusBorderColors = extractStatusBorderColors()

  const nodes = buildGroupNodes(allGroups, width, height)
  const svg = createSvgWithDefs(container, width, height)

  const groupContainers = svg
    .selectAll<SVGGElement, GroupNode>("g.group")
    .data(nodes)
    .join("g")
    .attr("class", "group")
    .style("cursor", "grab")

  groupContainers
    .append("circle")
    .attr("class", "outer-circle")
    .attr("r", d => d.radius)
    .style("fill", circleColor)
    .style("stroke", circleBorderColor)
    .style("stroke-width", "1px")

  const labelGroups = groupContainers
    .append("g")
    .attr("class", "group-label")
    .attr("transform", d => `translate(0, ${-d.radius})`)

  renderGroupBadgeLabel(labelGroups, badgeStyles)

  renderGoalCircles(groupContainers, statusBorderColors, container, callbacks.onGoalEnter, callbacks.onGoalLeave)

  // Force layout: gentle pull to center, collision so groups don't overlap, mild
  // repulsion to spread them, and a hard bounds clamp keeping every group inside
  // the viewport (with extra top padding for the group label pill).
  const simulation = d3
    .forceSimulation(nodes)
    .force("center", d3.forceCenter(width / 2, height / 2).strength(0.05))
    .force(
      "collision",
      d3.forceCollide<GroupNode>().radius(d => d.radius + 10)
    )
    .force("charge", d3.forceManyBody().strength(-50))
    .force("bounds", () => {
      const padding = 16
      for (const d of nodes) {
        d.x = Math.max(d.radius + padding, Math.min(width - d.radius - padding, d.x!))
        d.y = Math.max(d.radius + 20 + padding, Math.min(height - d.radius - padding, d.y!))
      }
    })

  groupContainers.call(createDragBehavior(simulation) as never)

  simulation.on("tick", () => {
    groupContainers.attr("transform", d => `translate(${d.x},${d.y})`)
  })

  return () => simulation.stop()
}
