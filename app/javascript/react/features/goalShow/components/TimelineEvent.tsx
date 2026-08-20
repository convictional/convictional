import { Markdown } from "~/react/composites/markdown/Markdown"
import { UserAvatar } from "~/react/composites/UserAvatar"
import { STATUS_CONFIG } from "~/react/shared/statusConfig"
import { DateTime } from "~/react/ui/DateTime"
import { formatISODate } from "~/shared/datetime"
import type { TimelineEvent as TimelineEventType } from "../types"
import { UpdateCardHeader } from "./UpdateCardHeader"

function EventBase({
  event,
  children,
  showDate = true,
}: {
  event: TimelineEventType
  children: React.ReactNode
  showDate?: boolean
}) {
  return (
    <div className="flex justify-between items-start flex-nowrap">
      <div className="text-sm text-base-content/60 flex-1 min-w-0">{children}</div>
      {showDate && (
        <DateTime
          datetime={event.created_at}
          format="relative"
          className="text-xs text-base-content/40 ml-4 whitespace-nowrap shrink-0"
        />
      )}
    </div>
  )
}

function GoalCreated({ event }: { event: TimelineEventType }) {
  return (
    <EventBase event={event}>
      <p>
        Goal created <By event={event} />
      </p>
    </EventBase>
  )
}

function GoalCompleted({ event }: { event: TimelineEventType }) {
  return (
    <EventBase event={event}>
      <p>
        Goal completed <By event={event} />
      </p>
    </EventBase>
  )
}

function GoalClosed({ event }: { event: TimelineEventType }) {
  return (
    <EventBase event={event}>
      <p>
        Goal closed <By event={event} />
      </p>
    </EventBase>
  )
}

function GoalReactivated({ event }: { event: TimelineEventType }) {
  return (
    <EventBase event={event}>
      <p>
        Goal reopened <By event={event} />
      </p>
    </EventBase>
  )
}

function GoalActivated({ event }: { event: TimelineEventType }) {
  return (
    <EventBase event={event}>
      <p>
        Goal reactivated <By event={event} />
      </p>
    </EventBase>
  )
}

function GoalDeleted({ event }: { event: TimelineEventType }) {
  return (
    <EventBase event={event}>
      <p>
        Goal deleted <By event={event} />
      </p>
    </EventBase>
  )
}

function By({ event }: { event: TimelineEventType }) {
  return <span className="text-base-content/40">by {event.creator?.display_name ?? "Convictional"}</span>
}

function formatStatus(status: string): string {
  return (
    STATUS_CONFIG[status]?.text ??
    status
      .split("_")
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  )
}

type Details = Record<string, unknown>
const VALUE_CLASS = "text-base-content/80"

function descriptionChange(d: Details): React.ReactNode | null {
  const desc = d.description as [string, string] | undefined
  if (!desc) return null
  const [prev, next] = desc
  if (!prev && next)
    return (
      <>
        Description set to <span className={VALUE_CLASS}>{next}</span>
      </>
    )
  return <>Description updated</>
}

function titleChange(d: Details): React.ReactNode | null {
  if (!d.title) return null
  const [, next] = d.title as [string, string]
  return (
    <>
      Renamed to <span className={VALUE_CLASS}>{next}</span>
    </>
  )
}

function completionChange(d: Details): React.ReactNode | null {
  if (!d.completed_at) return null
  const [, newVal] = d.completed_at as [unknown, unknown]
  return <>{newVal ? "Goal marked as completed" : "Goal re-opened"}</>
}

function ownerChange(d: Details, owner: TimelineEventType["owner"]): React.ReactNode | null {
  if (!d.owner_id) return null
  const [, newVal] = d.owner_id as [string | null, string | null]
  if (newVal && owner)
    return (
      <>
        Owner set to <span className={VALUE_CLASS}>{owner.display_name}</span>
      </>
    )
  return <>Owner removed</>
}

function groupChange(d: Details, group: TimelineEventType["group"]): React.ReactNode | null {
  if (!d.group_id) return null
  const [, newVal] = d.group_id as [string | null, string | null]
  if (newVal && group)
    return (
      <>
        Group set to <span className={VALUE_CLASS}>{group.name}</span>
      </>
    )
  return <>Group removed</>
}

function statusChange(d: Details): React.ReactNode | null {
  if (!d.status) return null
  const [, newStatus] = d.status as [string, string]
  return (
    <>
      Status changed to <span className={VALUE_CLASS}>{formatStatus(newStatus)}</span>
    </>
  )
}

function dateChange(d: Details, field: string, label: string): React.ReactNode | null {
  if (!d[field]) return null
  const [, newDate] = d[field] as [string | null, string | null]
  if (newDate)
    return (
      <>
        {label} set to <span className={VALUE_CLASS}>{formatISODate(newDate)}</span>
      </>
    )
  return <>{label} removed</>
}

function positionChange(d: Details): React.ReactNode | null {
  if (!("position" in d)) return null
  return <>Priority reordered</>
}

export function describeChanges(event: TimelineEventType): React.ReactNode[] {
  const d = event.details
  return [
    descriptionChange(d),
    titleChange(d),
    completionChange(d),
    ownerChange(d, event.owner),
    groupChange(d, event.group),
    statusChange(d),
    dateChange(d, "target_date", "Due date"),
    dateChange(d, "start_date", "Start date"),
    positionChange(d),
  ].filter((c): c is React.ReactNode => c !== null)
}

function GoalUpdated({ event }: { event: TimelineEventType }) {
  const changes = describeChanges(event)

  if (changes.length === 0) return null

  if (changes.length === 1) {
    return (
      <EventBase event={event}>
        <p>
          {changes[0]} <By event={event} />
        </p>
      </EventBase>
    )
  }

  return (
    <EventBase event={event}>
      <p>
        Goal updated <By event={event} />
      </p>
      <ul className="mt-0.5 space-y-px text-base-content/50">
        {changes.map((change, i) => (
          <li key={i}>{change}</li>
        ))}
      </ul>
    </EventBase>
  )
}

function GoalCommented({ event }: { event: TimelineEventType }) {
  return (
    <EventBase event={event} showDate={false}>
      <div>
        <CommentDisplay event={event} />
        {event.replies.map(reply => (
          <div key={reply.id} className="ml-2 border-l-2 border-base-300 pl-3 mt-2">
            <CommentDisplay event={reply} />
          </div>
        ))}
      </div>
    </EventBase>
  )
}

function CommentDisplay({ event }: { event: TimelineEventType }) {
  if (!event.comment) return null

  return (
    <div className="pt-2.5">
      <div className="flex items-start gap-2">
        {event.comment.user && (
          <div className="shrink-0">
            <UserAvatar user={event.comment.user} size="small" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-base-content">
              {event.comment.user?.display_name ?? "Unknown"}
            </span>
            <DateTime datetime={event.created_at} format="relative" className="text-xs text-base-content/40" />
          </div>
          <Markdown source={event.comment.content} variant="compact" className="text-sm text-base-content/80 mt-0.5" />
        </div>
      </div>
    </div>
  )
}

function GoalUpdatePosted({ event }: { event: TimelineEventType }) {
  if (!event.goal_update) return null

  const goalUpdate = event.goal_update

  const card = (
    <div className="relative mt-2">
      <div className="absolute left-3 -top-3 dropdown-card rounded-lg inline-flex items-center px-2 py-1 shadow-sm z-10">
        <span className="text-xs text-base-600/70 font-semibold">Update</span>
      </div>
      <div className="p-3 pt-5 border border-base-300 rounded-xl bg-base-50 shadow-xs relative overflow-hidden">
        <UpdateCardHeader
          creator={event.creator}
          status={goalUpdate.status}
          progress={goalUpdate.progress}
          createdAt={event.created_at}
          statusVariant="text"
          requestedBy={goalUpdate.requested_by}
        />

        <div className="mt-3">
          <div className="text-sm text-base-content/80">
            {goalUpdate.question_text && (
              <p className="text-base-content/50 text-xs mb-1.5">{goalUpdate.question_text}</p>
            )}
            {goalUpdate.answer_text && (
              <Markdown source={goalUpdate.answer_text} variant="compact" className="text-base-content mb-2" />
            )}
          </div>
        </div>
      </div>
    </div>
  )

  return (
    <EventBase event={event} showDate={false}>
      {card}
    </EventBase>
  )
}

const EVENT_RENDERERS: Record<string, React.ComponentType<{ event: TimelineEventType }>> = {
  goal_created: GoalCreated,
  goal_completed: GoalCompleted,
  goal_closed: GoalClosed,
  goal_reactivated: GoalReactivated,
  goal_activated: GoalActivated,
  goal_deleted: GoalDeleted,
  goal_updated: GoalUpdated,
  goal_commented: GoalCommented,
  goal_update_posted: GoalUpdatePosted,
}

export function TimelineEventRenderer({ event }: { event: TimelineEventType }) {
  const Renderer = EVENT_RENDERERS[event.action]
  if (!Renderer) return null

  return (
    <div id={`goal-event-${event.id}`}>
      <Renderer event={event} />
    </div>
  )
}
