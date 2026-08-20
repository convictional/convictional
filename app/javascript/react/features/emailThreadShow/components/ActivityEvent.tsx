import { memo } from "react"

import type { EmailThreadEvent } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"

interface ActivityEventProps {
  event: EmailThreadEvent
}

function eventContent(event: EmailThreadEvent): React.ReactNode {
  const creator = event.creator?.display_name ?? "Someone"
  const details = event.details

  switch (event.action) {
    case "assigned":
      return `${creator} assigned to ${(details?.type === "assigned" ? details.subject_label : null) ?? "someone"}`
    case "unassigned":
      return `${creator} unassigned ${(details?.type === "unassigned" ? details.subject_label : null) ?? "someone"}`
    case "added_collaborator": {
      const subject = details?.type === "added_collaborator" ? details.subject_label : null
      const reason = details?.type === "added_collaborator" ? details.reason : null
      return `${creator} invited ${subject ?? "a collaborator"} ${reason ?? "to collaborate."}`
    }
    default:
      // Actions without a structured detail payload render nothing.
      return null
  }
}

// Memoized to skip re-renders driven by unrelated parent state (e.g. the scroll
// listener flipping `autoScroll`); `event` is referentially stable across those.
export const ActivityEvent = memo(function ActivityEvent({ event }: ActivityEventProps) {
  const content = eventContent(event)
  if (content == null) return null

  return (
    <div data-event-id={event.id} className="flex justify-between items-center flex-nowrap">
      <div className="text-xs text-base-500 flex-1 min-w-0">{content}</div>
      <div className="text-xs text-base-500 ml-4 whitespace-nowrap shrink-0">
        <DateTime datetime={event.created_at} format="relative" />
      </div>
    </div>
  )
})
