import { Fragment, useMemo, useState } from "react"

import type { User } from "~/react/shared/types"
import { formatDateTime } from "~/react/ui/DateTime"

import type { TimelineEvent } from "../types"
import { SeenByAvatars } from "./SeenByAvatars"
import { describeChanges, TimelineEventRenderer } from "./TimelineEvent"

const EventAction = {
  GOAL_COMPLETED: "goal_completed",
  GOAL_UPDATE_POSTED: "goal_update_posted",
  GOAL_COMMENTED: "goal_commented",
  GOAL_UPDATED: "goal_updated",
  GOAL_UPDATE_REQUESTED: "goal_update_requested",
} as const

const GoalStatus = {
  ON_TRACK: "on_track",
  AT_RISK: "at_risk",
  OFF_TRACK: "off_track",
} as const

type GoalStatus = (typeof GoalStatus)[keyof typeof GoalStatus]

export interface StatusStyle {
  icon: string
  color: string
  bg: string
  border: string
  line: string
  dot: string
}

const COMPLETED_STYLE: StatusStyle = {
  icon: "emoji_events",
  color: "text-primary",
  bg: "bg-primary/10",
  border: "border-primary/50",
  line: "bg-primary/50",
  dot: "border-primary",
}

const STATUS_STYLES: Record<GoalStatus, StatusStyle> = {
  on_track: {
    icon: "check",
    color: "text-success-content",
    bg: "bg-success-content/10",
    border: "border-success-content/50",
    line: "bg-success-content/50",
    dot: "border-success-content",
  },
  at_risk: {
    icon: "warning",
    color: "text-warning-content",
    bg: "bg-warning-content/10",
    border: "border-warning-content/50",
    line: "bg-warning-content/50",
    dot: "border-warning-content",
  },
  off_track: {
    icon: "error",
    color: "text-error-content",
    bg: "bg-error-content/10",
    border: "border-error-content/50",
    line: "bg-error-content/50",
    dot: "border-error-content",
  },
}

export function getStatusStyle(status: string): StatusStyle | undefined {
  if (status in STATUS_STYLES) return STATUS_STYLES[status as GoalStatus]
  return undefined
}

export const DEFAULT_LINE = "bg-base-content/15"
const DEFAULT_DOT = "border-base-content/30"

type StatusMarker = { icon: string; color: string; bg: string; border: string }

const COMMENT_MARKER: StatusMarker = {
  icon: "chat_bubble",
  color: "text-base-content/50",
  bg: "bg-base-content/5",
  border: "border-base-content/20",
}

const CALENDAR_MARKER: StatusMarker = {
  icon: "calendar_today",
  color: "text-base-content/50",
  bg: "bg-base-content/5",
  border: "border-base-content/20",
}

function isCompletionEvent(event: TimelineEvent): boolean {
  if (event.action === EventAction.GOAL_COMPLETED) return true
  if (event.action === EventAction.GOAL_UPDATE_POSTED && event.details.is_completed) return true
  return false
}

// Resolve the effective status key from an event, or null if it doesn't change status
function getEventStatus(event: TimelineEvent): string | null {
  if (isCompletionEvent(event)) return GoalStatus.ON_TRACK

  if (event.action === EventAction.GOAL_UPDATE_POSTED && event.goal_update) {
    return event.goal_update.status
  }

  const statusChange = event.details.status as [string, string] | undefined
  if (statusChange) return statusChange[1]

  return null
}

function getStatusMarker(event: TimelineEvent): StatusMarker | null {
  if (isCompletionEvent(event)) return COMPLETED_STYLE
  if (event.action === EventAction.GOAL_COMMENTED) return COMMENT_MARKER
  if (event.action === EventAction.GOAL_UPDATED && event.details.target_date) return CALENDAR_MARKER

  const status = getEventStatus(event)
  if (!status) return null
  return getStatusStyle(status) ?? null
}

// Compute [lineAbove, lineBelow, dotColor] per event based on status progression
function computeEventColors(events: TimelineEvent[]): Map<string, [string, string, string]> {
  const colors = new Map<string, [string, string, string]>()
  let currentLine = DEFAULT_LINE
  let currentDot = DEFAULT_DOT

  for (let i = 0; i < events.length; i++) {
    const event = events[i]
    const above = currentLine

    const newStatus = getEventStatus(event)
    if (newStatus) {
      const style = getStatusStyle(newStatus)
      currentLine = style?.line ?? DEFAULT_LINE
      currentDot = style?.dot ?? DEFAULT_DOT
    }

    colors.set(event.id, [above, currentLine, currentDot])
  }

  return colors
}

// computeEventColors walks chronological order, but the timeline renders newest-first — so the
// "above" and "below" line colors must be swapped for display. Centralised here so no render
// branch can silently forget the swap.
function displayColors(colors: [string, string, string] | undefined): {
  lineAbove: string
  lineBelow: string
  dotColor: string
} {
  const [chronoAbove, chronoBelow, dotColor] = colors ?? [DEFAULT_LINE, DEFAULT_LINE, DEFAULT_DOT]
  return { lineAbove: chronoBelow, lineBelow: chronoAbove, dotColor }
}

type DisplayItem =
  | { kind: "event"; event: TimelineEvent }
  | { kind: "group"; groupKind: "description" | "due_date" | "rename"; events: TimelineEvent[]; groupKey: string }

// Only collapse events where the sole change is a description edit (prev must be non-empty).
function isDescriptionOnlyUpdate(event: TimelineEvent): boolean {
  if (event.action !== EventAction.GOAL_UPDATED) return false
  const d = event.details
  const desc = d.description as [string, string] | undefined
  if (!desc || !desc[0]) return false
  return !d.title && !d.owner_id && !d.group_id && !d.status && !d.target_date && !d.start_date && !d.completed_at
}

// Only collapse events where the sole change is a due-date update.
function isDueDateOnlyChange(event: TimelineEvent): boolean {
  if (event.action !== EventAction.GOAL_UPDATED) return false
  const d = event.details
  return (
    !!d.target_date &&
    !d.description &&
    !d.title &&
    !d.owner_id &&
    !d.group_id &&
    !d.status &&
    !d.start_date &&
    !d.completed_at
  )
}

// Only collapse events where the sole change is a title rename.
function isRenameOnlyUpdate(event: TimelineEvent): boolean {
  if (event.action !== EventAction.GOAL_UPDATED) return false
  const d = event.details
  return (
    !!d.title &&
    !d.description &&
    !d.owner_id &&
    !d.group_id &&
    !d.status &&
    !d.target_date &&
    !d.start_date &&
    !d.completed_at
  )
}

function sameDayStr(a: string, b: string): boolean {
  return a.slice(0, 10) === b.slice(0, 10)
}

function sameAuthor(a: TimelineEvent, b: TimelineEvent): boolean {
  return (a.creator?.id ?? null) === (b.creator?.id ?? null)
}

// A trivial-event kind that collapses into a single summary row. `matches` selects events of the
// kind; `sameRun` decides whether a later match belongs in the same run as the run's first event.
interface TrivialRule {
  groupKind: "description" | "due_date" | "rename"
  matches: (event: TimelineEvent) => boolean
  sameRun: (first: TimelineEvent, candidate: TimelineEvent) => boolean
}

// Collapse rules (Variant C):
//   - 2+ consecutive description-only edits by the same author → collapse
//   - 2+ consecutive due-date-only changes within the same calendar day → collapse
//   - 2+ consecutive renames by the same author → collapse
//   - Everything else stays visible (hero updates, comments, status changes, etc.)
const TRIVIAL_RULES: TrivialRule[] = [
  { groupKind: "description", matches: isDescriptionOnlyUpdate, sameRun: sameAuthor },
  { groupKind: "due_date", matches: isDueDateOnlyChange, sameRun: (a, b) => sameDayStr(a.created_at, b.created_at) },
  { groupKind: "rename", matches: isRenameOnlyUpdate, sameRun: sameAuthor },
]

function groupTrivialEvents(events: TimelineEvent[]): DisplayItem[] {
  const items: DisplayItem[] = []
  let i = 0
  while (i < events.length) {
    const event = events[i]
    const rule = TRIVIAL_RULES.find(r => r.matches(event))

    if (rule) {
      const run: TimelineEvent[] = [event]
      while (i + 1 < events.length && rule.matches(events[i + 1]) && rule.sameRun(event, events[i + 1])) {
        i++
        run.push(events[i])
      }
      if (run.length >= 2) {
        items.push({ kind: "group", groupKind: rule.groupKind, events: run, groupKey: run[run.length - 1].id })
      } else {
        items.push({ kind: "event", event })
      }
    } else {
      items.push({ kind: "event", event })
    }
    i++
  }
  return items
}

// The line + dot rail rendered to the left of every timeline row. `marker` swaps the plain dot for
// an icon disc; `topLine` is the class for the short connector above the dot, or false to omit that
// segment entirely (first row, or icon discs that butt straight against the row above).
function TimelineMarkerColumn({
  marker,
  dotColor,
  topLine,
  bottomLine,
}: {
  marker: StatusMarker | null
  dotColor: string
  topLine: string | false
  bottomLine: string
}) {
  return (
    <div className="flex flex-col items-center w-6 shrink-0">
      {topLine !== false && <div className={`w-px h-2 ${topLine}`} />}
      {marker ? (
        <div
          className={`relative z-10 flex items-center justify-center w-6 h-6 rounded-full border shrink-0 ${marker.bg} ${marker.border}`}
        >
          <span className={`material-symbols-outlined ${marker.color}`} style={{ fontSize: "14px" }}>
            {marker.icon}
          </span>
        </div>
      ) : (
        <div
          className={`relative z-10 w-[9px] h-[9px] rounded-full shrink-0 bg-base-100 border-[1.5px] ${dotColor}`}
        />
      )}
      <div className={`w-px flex-1 ${bottomLine}`} />
    </div>
  )
}

interface GoalTimelineProps {
  events: TimelineEvent[]
  lastSeenEventId: string | null
  readersByEventId: Map<string, User[]>
}

export function GoalTimeline({ events, lastSeenEventId, readersByEventId }: GoalTimelineProps) {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())

  const renderableEvents = useMemo(
    () =>
      events.filter(e => {
        if (e.action === EventAction.GOAL_UPDATE_REQUESTED) return false
        if (e.action === EventAction.GOAL_UPDATED && describeChanges(e).length === 0) return false
        return true
      }),
    [events]
  )
  // Color computation walks chronological order; display is reversed (newest first).
  const eventColors = useMemo(() => computeEventColors(renderableEvents), [renderableEvents])
  const displayEvents = useMemo(() => [...renderableEvents].reverse(), [renderableEvents])

  if (renderableEvents.length === 0) {
    if (events.length === 0) {
      return <p className="text-sm text-base-content/40 py-2">No activity yet</p>
    }
    return null
  }

  // Suppress the "New activity" divider when the viewer is caught up: if their last-seen event is the
  // newest one, nothing sits above the line and a "New activity" label would be misleading.
  const newestEventId = displayEvents[0]?.id ?? null
  const hasLastSeen =
    lastSeenEventId !== null && lastSeenEventId !== newestEventId && events.some(e => e.id === lastSeenEventId)

  const displayItems = groupTrivialEvents(displayEvents)
  return (
    <div className="w-full mt-3 px-4">
      {displayItems.map((item, itemIndex) => {
        const isFirst = itemIndex === 0
        const isLast = itemIndex === displayItems.length - 1

        if (item.kind === "group") {
          const isExpanded = expandedGroups.has(item.groupKey)
          const count = item.events.length
          const toggle = () =>
            setExpandedGroups(prev => {
              const next = new Set(prev)
              if (isExpanded) next.delete(item.groupKey)
              else next.add(item.groupKey)
              return next
            })
          const { lineAbove, lineBelow, dotColor } = displayColors(eventColors.get(item.events[0].id))
          return (
            <Fragment key={item.groupKey}>
              <div className="relative flex gap-4">
                <TimelineMarkerColumn
                  marker={null}
                  dotColor={dotColor}
                  topLine={!isFirst ? lineAbove : ""}
                  bottomLine={!isLast || isExpanded ? lineBelow : ""}
                />
                <div className="flex-1 min-w-0 pb-5">
                  <button
                    type="button"
                    onClick={toggle}
                    className="text-sm text-base-content/40 hover:text-base-content/60 transition-colors"
                  >
                    {item.groupKind === "description" ? (
                      <>
                        Description edited {count} times by {item.events[0].creator?.display_name ?? "unknown"}
                      </>
                    ) : item.groupKind === "rename" ? (
                      <>
                        Renamed {count} times by {item.events[0].creator?.display_name ?? "unknown"}
                      </>
                    ) : (
                      <>
                        {(() => {
                          const change = item.events[0].details.target_date as
                            [string | null, string | null] | undefined
                          const finalDate = change?.[1]
                          return finalDate
                            ? `Due date changed ${count} times → ${formatDateTime(finalDate, "date_medium")}`
                            : `Due date removed ${count} times`
                        })()}
                      </>
                    )}{" "}
                    &middot; {isExpanded ? "Hide" : "Show"}
                  </button>
                </div>
              </div>
              {isExpanded &&
                item.events.map((event, ei) => {
                  const isEventLast = isLast && ei === item.events.length - 1
                  const { lineAbove, lineBelow, dotColor } = displayColors(eventColors.get(event.id))
                  const marker = getStatusMarker(event)
                  return (
                    <div key={event.id} className="relative flex gap-4">
                      <TimelineMarkerColumn
                        marker={marker}
                        dotColor={dotColor}
                        topLine={marker ? false : lineAbove}
                        bottomLine={!isEventLast ? lineBelow : ""}
                      />
                      <div
                        className={`flex-1 min-w-0 pb-5 ${marker ? (event.action === EventAction.GOAL_COMMENTED ? "pt-2.5" : "pt-2") : ""}`}
                      >
                        <TimelineEventRenderer event={event} />
                      </div>
                    </div>
                  )
                })}
            </Fragment>
          )
        }

        const event = item.event
        // lastSeenEventId is the newest event the viewer already saw, so it belongs below the line.
        // Display is newest-first, so render the separator ABOVE that row: unseen events sit above
        // it, the last-seen event and everything older below.
        const showNewActivitySeparator = hasLastSeen && event.id === lastSeenEventId
        const marker = getStatusMarker(event)
        const { lineAbove, lineBelow, dotColor } = displayColors(eventColors.get(event.id))

        return (
          <Fragment key={event.id}>
            {showNewActivitySeparator && <NewActivitySeparator />}
            <div className="relative flex gap-4">
              <TimelineMarkerColumn
                marker={marker}
                dotColor={dotColor}
                topLine={!isFirst ? lineAbove : ""}
                bottomLine={!isLast ? lineBelow : ""}
              />
              <div
                className={`flex-1 min-w-0 pb-5 ${marker ? (event.action === EventAction.GOAL_COMMENTED ? "pt-2.5" : "pt-2") : ""}`}
              >
                <TimelineEventRenderer event={event} />
                <SeenByAvatars readers={readersByEventId.get(event.id) ?? []} />
              </div>
            </div>
          </Fragment>
        )
      })}
    </div>
  )
}

function NewActivitySeparator() {
  return (
    <div className="relative flex gap-4">
      <div className="flex flex-col items-center w-6 shrink-0">
        <div className="w-px flex-1 bg-primary/20" />
      </div>
      <div className="flex-1 min-w-0 py-1">
        <div className="flex items-center gap-2">
          <div className="flex-1 border-t border-primary/20" />
          <p className="text-primary/60 text-xs whitespace-nowrap">New activity</p>
          <div className="flex-1 border-t border-primary/20" />
        </div>
      </div>
    </div>
  )
}
