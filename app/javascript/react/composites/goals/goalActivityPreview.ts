import {
  type ActivityContext,
  describeCrossResourceActivity,
} from "~/react/composites/mailboxPreview/crossResourceActivity"
import { STATUS_CONFIG } from "~/react/shared/statusConfig"
import type { EventAction } from "~/react/shared/types"

type Details = Record<string, unknown>

// A phrased activity line. `date` is a raw ISO value, present only for due/start-date changes, that
// the caller renders via UserDateTime; every other line is fully phrased in `text`.
export interface GoalActivityPreview {
  text: string
  date?: string
}

export interface GoalActivityContext extends ActivityContext {
  resolveUserName?: (id: string) => string | undefined
  resolveGroupName?: (id: string) => string | undefined
}

// Second element of an Event.details `[old, new]` diff pair, or undefined.
function newValue(change: unknown): unknown {
  return Array.isArray(change) && change.length === 2 ? change[1] : undefined
}

function describeGoalUpdated(details: Details, context: GoalActivityContext): GoalActivityPreview {
  if (newValue(details.completed_at)) return { text: "Goal marked completed" }
  if ("completed_at" in details) return { text: "Goal reopened" }
  if ("title" in details) return { text: "Goal title changed" }
  const status = newValue(details.status)
  if (typeof status === "string" && STATUS_CONFIG[status])
    return { text: `Status changed to ${STATUS_CONFIG[status].text}` }
  if ("owner_id" in details) {
    const id = newValue(details.owner_id)
    const name = typeof id === "string" ? context.resolveUserName?.(id) : undefined
    return { text: name ? `Owner changed to ${name}` : "Owner changed" }
  }
  if ("group_id" in details) {
    const id = newValue(details.group_id)
    const name = typeof id === "string" ? context.resolveGroupName?.(id) : undefined
    return { text: name ? `Group changed to ${name}` : "Group changed" }
  }
  if ("target_date" in details) {
    const date = newValue(details.target_date)
    return typeof date === "string" ? { text: "Due date changed to", date } : { text: "Due date changed" }
  }
  if ("start_date" in details) {
    const date = newValue(details.start_date)
    return typeof date === "string" ? { text: "Start date changed to", date } : { text: "Start date changed" }
  }
  if ("description" in details) return { text: "Description updated" }
  if ("position" in details) return { text: "Priority reordered" }
  return { text: "Goal updated" }
}

const ACTIVITY_MESSAGES: Partial<Record<EventAction, string>> = {
  goal_created: "Goal created",
  goal_completed: "Goal marked completed",
  goal_closed: "Goal closed",
  goal_reactivated: "Goal reopened",
  goal_activated: "Goal reactivated",
  goal_deleted: "Goal deleted",
}

export function describeGoalActivity(
  action: EventAction | null,
  details: Details | null,
  context: GoalActivityContext = {}
): GoalActivityPreview {
  const shared = describeCrossResourceActivity(action, details ?? {}, context)
  if (shared) return { text: shared }
  if (action === "goal_updated") return describeGoalUpdated(details ?? {}, context)
  if (action === "goal_update_requested") {
    const question = typeof details?.question_text === "string" ? details.question_text : ""
    const prefix = context.actorName ? `Update requested from ${context.actorName}` : "Update requested"
    return { text: question ? `${prefix} - ${question}` : prefix }
  }
  return { text: (action && ACTIVITY_MESSAGES[action]) || "Goal updated" }
}
