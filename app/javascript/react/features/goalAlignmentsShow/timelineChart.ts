import * as d3 from "d3"

import type { AlignmentTimelineData, TimelineProgressEvent, TimelineStatusChange, WeeklyActivityBucket } from "./types"

// React owns the container <div>/ref; this module owns all the D3 math and SVG
// construction, run imperatively from an effect. The pure layout/bucketing helpers
// are exported so the geometry can be unit-tested against fixed data, locking the
// math against silent drift. Inputs are snake_case (the JSON API contract); internal
// computed points stay camelCase as local data.

interface ChartLayout {
  width: number
  height: number
  chartHeight: number
  weekWidth: number
  barWidth: number
  markerRadius: number
  markerPadding: number
  xScale: (weekIndex: number) => number
  xCenter: (weekIndex: number) => number
  yBarScale: d3.ScaleLinear<number, number>
  yProgressScale: d3.ScaleLinear<number, number>
}

interface ChartColors {
  statusColors: Record<string, string>
  baseColor: string
  barFillColor: string
  labelColor: string
}

interface TooltipController {
  show(x: number, anchorTop: number, anchorBottom: number, text: string, html?: boolean): void
  hide(): void
}

interface ProgressPoint {
  weekIndex: number
  progress: number
}

type StatusMarker = { weekIndex: number; value: number; status: string }

const STATUS_DOT_CLASSES: Record<string, string> = {
  on_track: "bg-success-content",
  at_risk: "bg-warning-content",
  off_track: "bg-error-content",
}

const STATUS_ICONS: Record<string, string> = {
  on_track: "check",
  at_risk: "warning",
  off_track: "error",
}

const STATUS_LABELS: Record<string, string> = {
  on_track: "On Track",
  at_risk: "At Risk",
  off_track: "Off Track",
}

// Colors come from the daisyUI theme, which only exists as resolved CSS on a
// mounted element — so we read them off a throwaway hidden node rather than
// hardcoding hex values that would drift from the theme.
function readComputedStyle(className: string, property: keyof CSSStyleDeclaration): string {
  const el = document.createElement("div")
  el.className = className
  el.style.position = "absolute"
  el.style.visibility = "hidden"
  document.body.appendChild(el)
  const value = getComputedStyle(el)[property] as string
  document.body.removeChild(el)
  return value
}

function extractStatusColors(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(STATUS_DOT_CLASSES).map(([status, className]) => [
      status,
      readComputedStyle(className, "backgroundColor"),
    ])
  )
}

function extractChartColors(): ChartColors {
  return {
    statusColors: extractStatusColors(),
    baseColor: readComputedStyle("text-base-400", "color"),
    barFillColor: readComputedStyle("bg-base-300", "backgroundColor"),
    labelColor: readComputedStyle("text-base-500", "color"),
  }
}

function parseRgb(color: string): [number, number, number] | null {
  const match = color.match(/\d+/g)
  if (!match || match.length < 3) return null
  return [Number(match[0]), Number(match[1]), Number(match[2])]
}

// Status marker fill is a 25%-toward-the-status-color tint of white, so the
// material icon (drawn in the full status color) stays legible on top.
function blendWithWhite(color: string, ratio: number): string {
  const rgb = parseRgb(color)
  if (!rgb) return "rgb(200, 240, 215)"
  return `rgb(${Math.round(rgb[0] * ratio + 255 * (1 - ratio))}, ${Math.round(rgb[1] * ratio + 255 * (1 - ratio))}, ${Math.round(rgb[2] * ratio + 255 * (1 - ratio))})`
}

// The progress line is anchored at 0% in week 0 and ends at the goal's current
// progress in today's week, with each recorded update as a point in between.
export function buildProgressEvents(
  progressEvents: TimelineProgressEvent[],
  currentProgress: number,
  todayWeekIndex: number
): ProgressPoint[] {
  const eventPoints: ProgressPoint[] = []
  eventPoints.push({ weekIndex: 0, progress: 0 })

  for (const event of progressEvents) {
    eventPoints.push({ weekIndex: event.week_index, progress: event.progress })
  }

  eventPoints.push({ weekIndex: todayWeekIndex, progress: currentProgress })

  return eventPoints
}

// Progress is a step function: each event's value holds (as a flat segment) from
// its own week until the week before the next event, then jumps. Weeks before the
// first event / after the last stay null (no line drawn there).
export function interpolateProgress(eventPoints: ProgressPoint[], totalWeeks: number): (number | null)[] {
  const progressData: (number | null)[] = new Array(totalWeeks).fill(null)

  for (let i = 0; i < eventPoints.length; i++) {
    const current = eventPoints[i]
    const next = eventPoints[i + 1]
    const endWeek = next ? next.weekIndex - 1 : current.weekIndex

    for (let j = current.weekIndex; j <= endWeek && j < totalWeeks; j++) {
      progressData[j] = current.progress * 100
    }

    if (next) {
      progressData[next.weekIndex] = next.progress * 100
    }
  }

  return progressData
}

// Builds the polyline points for the step function: a point at each event, plus a
// horizontal hold point at (next.weekIndex - 1) whenever the next event is more
// than one week away, so the line stays flat then steps rather than sloping.
export function buildProgressLinePoints(eventPoints: ProgressPoint[], layout: ChartLayout): [number, number][] {
  const points: [number, number][] = []

  for (let i = 0; i < eventPoints.length; i++) {
    const current = eventPoints[i]
    const next = eventPoints[i + 1]

    points.push([layout.xCenter(current.weekIndex), layout.yProgressScale(current.progress * 100)])

    if (next && next.weekIndex > current.weekIndex + 1) {
      points.push([layout.xCenter(next.weekIndex - 1), layout.yProgressScale(current.progress * 100)])
    }
  }

  return points
}

// A status change is only drawn where the progress line actually exists (the week
// has an interpolated value), so a status marker never floats over an empty gap.
export function buildStatusMarkers(
  statusChanges: TimelineStatusChange[],
  progressData: (number | null)[]
): StatusMarker[] {
  return statusChanges
    .filter(sc => sc.week_index < progressData.length && progressData[sc.week_index] !== null)
    .map(sc => ({ weekIndex: sc.week_index, value: progressData[sc.week_index] as number, status: sc.status }))
}

// weekWidth divides the full width evenly across every week; bars are 70% of a
// week (min 4px) and centered. The y-bar domain tops out at 1.5× the busiest
// week so the tallest bar fills ~two-thirds of the height, leaving headroom for
// the progress line. The progress scale is inset by markerPadding so a status
// marker circle at 0% or 100% isn't clipped by the chart edges.
export function buildLayout(
  width: number,
  height: number,
  maxActivity: number,
  progressData: (number | null)[]
): ChartLayout {
  const markerRadius = 14
  const markerPadding = markerRadius + 4
  const xAxisHeight = 20
  const chartHeight = height - xAxisHeight

  const yMin = 0
  const yMax = 100

  const weekWidth = width / progressData.length
  const barWidth = Math.max(weekWidth * 0.7, 4)

  return {
    width,
    height,
    chartHeight,
    weekWidth,
    barWidth,
    markerRadius,
    markerPadding,
    xScale: (weekIndex: number) => weekIndex * weekWidth,
    xCenter: (weekIndex: number) => weekIndex * weekWidth + weekWidth / 2,
    yBarScale: d3
      .scaleLinear()
      .domain([0, maxActivity * 1.5])
      .range([chartHeight, 0]),
    yProgressScale: d3
      .scaleLinear()
      .domain([yMin, yMax])
      .range([chartHeight - markerPadding, markerPadding]),
  }
}

function createSvg(
  container: HTMLElement,
  width: number,
  height: number
): d3.Selection<SVGSVGElement, unknown, null, undefined> {
  return d3
    .select(container)
    .append("svg")
    .attr("width", "100%")
    .attr("height", "100%")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "none")
}

function createTooltip(container: HTMLElement, colors: ChartColors): TooltipController {
  container.style.position = "relative"
  container.style.overflow = "hidden"

  const tooltip = d3
    .select(container)
    .append("div")
    .style("position", "absolute")
    .style("pointer-events", "none")
    .style("opacity", "0")
    .style("font-size", "11px")
    .style("padding", "2px 6px")
    .style("border-radius", "4px")
    .style("background", colors.barFillColor)
    .style("color", colors.labelColor)
    .style("white-space", "nowrap")
    .style("box-shadow", "0 1px 3px rgba(0, 0, 0, 0.08)")

  return {
    show(x: number, anchorTop: number, anchorBottom: number, text: string, html = false) {
      tooltip.style("opacity", "1").style("left", "0").style("top", "0").style("transform", "none")
      if (html) tooltip.html(text)
      else tooltip.text(text)

      const el = tooltip.node() as HTMLElement
      // Clamp horizontally inside the container, and flip below the anchor if
      // there isn't room above it.
      const clampedLeft = Math.max(0, Math.min(x - el.offsetWidth / 2, container.clientWidth - el.offsetWidth))
      const above = anchorTop - el.offsetHeight - 4
      const top = above < 0 ? anchorBottom + 4 : above
      tooltip.style("left", `${clampedLeft}px`).style("top", `${top}px`)
    },
    hide() {
      tooltip.style("opacity", "0")
    },
  }
}

type BarDatum = WeeklyActivityBucket & { weekIndex: number }

function renderActivityBars(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  layout: ChartLayout,
  bars: BarDatum[],
  colors: ChartColors,
  tooltip: TooltipController
): void {
  svg
    .selectAll("rect.activity-bar")
    .data(bars)
    .join("rect")
    .attr("class", "activity-bar")
    .attr("x", d => layout.xCenter(d.weekIndex) - layout.barWidth / 2)
    .attr("y", d => layout.yBarScale(d.count))
    .attr("width", layout.barWidth)
    .attr("height", d => layout.chartHeight - layout.yBarScale(d.count))
    .attr("rx", 4)
    .attr("ry", 4)
    .attr("fill", colors.barFillColor)
    .attr("stroke", colors.baseColor)
    .attr("stroke-width", 1)
    .style("cursor", "pointer")
    .on("mouseenter", function (_event, d) {
      tooltip.show(
        layout.xCenter(d.weekIndex),
        layout.yBarScale(d.count),
        layout.chartHeight,
        `${d.count} aligned activity this week`
      )
    })
    .on("mouseleave", function () {
      tooltip.hide()
    })
}

// Dashed vertical divider marking the boundary between past and future weeks.
// Skipped when today is the last (or beyond) week, since there's no future to divide off.
function renderTodayDividerLine(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  layout: ChartLayout,
  colors: ChartColors,
  todayWeekIndex: number,
  totalWeeks: number
): void {
  if (todayWeekIndex >= totalWeeks - 1) return

  const todayX = layout.xScale(todayWeekIndex + 1)
  svg
    .append("line")
    .attr("x1", todayX)
    .attr("y1", 0)
    .attr("x2", todayX)
    .attr("y2", layout.chartHeight)
    .attr("stroke", colors.baseColor)
    .attr("stroke-width", 1.5)
    .attr("stroke-dasharray", "6 4")
    .attr("opacity", 0.6)
}

function renderProgressLine(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  colors: ChartColors,
  linePoints: [number, number][]
): void {
  if (linePoints.length <= 1) return

  const line = d3
    .line<[number, number]>()
    .x(d => d[0])
    .y(d => d[1])
    .curve(d3.curveMonotoneX)

  svg
    .append("path")
    .datum(linePoints)
    .attr("fill", "none")
    .attr("stroke", colors.baseColor)
    .attr("stroke-width", 1.5)
    .attr("d", line)
}

// Plain progress dots are drawn for every event point that isn't already shown as
// a (larger) status marker, so the two don't overlap on the same week.
function renderProgressDots(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  layout: ChartLayout,
  colors: ChartColors,
  eventPoints: ProgressPoint[],
  statusWeekIndices: Set<number>,
  tooltip: TooltipController
): void {
  const dots = eventPoints
    .filter(d => !statusWeekIndices.has(d.weekIndex))
    .map(d => ({ weekIndex: d.weekIndex, value: d.progress * 100 }))

  svg
    .selectAll("circle.progress-dot")
    .data(dots)
    .join("circle")
    .attr("class", "progress-dot")
    .attr("cx", d => layout.xCenter(d.weekIndex))
    .attr("cy", d => layout.yProgressScale(d.value))
    .attr("r", 4)
    .attr("fill", colors.labelColor)
    .attr("opacity", 0.6)
    .style("cursor", "pointer")
    .on("mouseenter", function (_event, d) {
      d3.select(this).attr("opacity", 1).attr("r", 5)
      tooltip.show(
        layout.xCenter(d.weekIndex),
        layout.yProgressScale(d.value) - 5,
        layout.yProgressScale(d.value) + 5,
        `${Math.round(d.value)}% progress`
      )
    })
    .on("mouseleave", function () {
      d3.select(this).attr("opacity", 0.6).attr("r", 4)
      tooltip.hide()
    })
}

function renderStatusMarkers(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  layout: ChartLayout,
  colors: ChartColors,
  statusMarkers: StatusMarker[],
  tooltip: TooltipController
): void {
  const markers = svg
    .selectAll("g.status-marker")
    .data(statusMarkers)
    .join("g")
    .attr("class", "status-marker")
    .attr("transform", d => `translate(${layout.xCenter(d.weekIndex)}, ${layout.yProgressScale(d.value)})`)

  markers
    .append("circle")
    .attr("r", layout.markerRadius)
    .attr("fill", d => blendWithWhite(colors.statusColors[d.status] || colors.statusColors.on_track, 0.25))
    .attr("stroke", d => colors.statusColors[d.status] || colors.statusColors.on_track)
    .attr("stroke-width", 1)

  markers
    .append("text")
    .attr("class", "material-symbols-outlined")
    .attr("text-anchor", "middle")
    .attr("dominant-baseline", "central")
    .style("font-size", "14px")
    .attr("fill", d => colors.statusColors[d.status] || colors.statusColors.on_track)
    .style("pointer-events", "none")
    .text(d => STATUS_ICONS[d.status] || STATUS_ICONS.on_track)

  markers
    .style("cursor", "pointer")
    .on("mouseenter", function (_event, d) {
      d3.select(this)
        .select("circle")
        .attr("r", layout.markerRadius + 2)
      const label = (STATUS_LABELS[d.status] || STATUS_LABELS.on_track).toLowerCase()
      tooltip.show(
        layout.xCenter(d.weekIndex),
        layout.yProgressScale(d.value) - layout.markerRadius,
        layout.yProgressScale(d.value) + layout.markerRadius,
        `Status changed to ${label}<br>${Math.round(d.value)}% progress`,
        true
      )
    })
    .on("mouseleave", function () {
      d3.select(this).select("circle").attr("r", layout.markerRadius)
      tooltip.hide()
    })
}

// First and last labels show the true start/end dates; interior labels show each
// week's Monday. All are center-anchored.
function renderXAxisLabels(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  layout: ChartLayout,
  colors: ChartColors,
  weeklyActivity: WeeklyActivityBucket[],
  totalWeeks: number,
  startDate: string,
  endDate: string
): void {
  const formatLabel = d3.timeFormat("%b %-d")
  const allLabels = weeklyActivity.map((w, i) => ({
    weekIndex: i,
    date:
      i === 0
        ? new Date(startDate + "T00:00:00")
        : i === totalWeeks - 1
          ? new Date(endDate + "T00:00:00")
          : new Date(w.week + "T00:00:00"),
  }))

  svg
    .selectAll("text.week-label")
    .data(allLabels)
    .join("text")
    .attr("class", "week-label")
    .attr("x", d => layout.xCenter(d.weekIndex))
    .attr("y", layout.chartHeight + 14)
    .attr("text-anchor", "middle")
    .style("font-size", "10px")
    .attr("fill", colors.labelColor)
    .text(d => formatLabel(d.date))
}

// Renders the whole chart into `container` at the given pixel size. Clears any
// prior render first so it's safe to call on resize. No-ops on an empty timeline.
export function renderTimelineChart(
  container: HTMLElement,
  data: AlignmentTimelineData,
  width: number,
  height: number
): void {
  container.innerHTML = ""

  const {
    weekly_activity: weeklyActivity,
    progress_events: progressEvents,
    status_changes: statusChanges,
    current_progress: currentProgress,
    total_weeks: totalWeeks,
    today_week_index: todayWeekIndex,
    start_date: startDate,
    end_date: endDate,
  } = data

  if (totalWeeks === 0) return

  const colors = extractChartColors()
  const maxActivity = Math.max(...weeklyActivity.map(w => w.count), 1)
  const eventPoints = buildProgressEvents(progressEvents, currentProgress, todayWeekIndex)
  const progressData = interpolateProgress(eventPoints, totalWeeks)
  const statusMarkers = buildStatusMarkers(statusChanges, progressData)

  const layout = buildLayout(width, height, maxActivity, progressData)
  const svg = createSvg(container, width, height)
  const tooltip = createTooltip(container, colors)

  const barsWithIndex = weeklyActivity.map((w, i) => ({ ...w, weekIndex: i })).filter(w => w.count > 0)
  const linePoints = buildProgressLinePoints(eventPoints, layout)

  renderActivityBars(svg, layout, barsWithIndex, colors, tooltip)
  renderTodayDividerLine(svg, layout, colors, todayWeekIndex, totalWeeks)
  renderProgressLine(svg, colors, linePoints)

  const statusWeekIndices = new Set(statusMarkers.map(m => m.weekIndex))
  renderProgressDots(svg, layout, colors, eventPoints, statusWeekIndices, tooltip)
  renderStatusMarkers(svg, layout, colors, statusMarkers, tooltip)
  renderXAxisLabels(svg, layout, colors, weeklyActivity, totalWeeks, startDate, endDate)
}
