import type { MeetingAttendeeStatus, User } from "~/react/shared/types"
import { Tooltip } from "~/react/ui/Tooltip"

interface MeetingAttendeesProps {
  resolved: User[]
  unresolved: MeetingAttendeeStatus[]
}

// A single grouped avatar showing total attendee count with a hover tooltip
// listing names. Used by MeetingCard on both the past list and collection
// show pages.
export function MeetingAttendees({ resolved, unresolved }: MeetingAttendeesProps) {
  const total = resolved.length + unresolved.length
  if (total === 0) return null

  const names = [...resolved.map(u => u.display_name), ...unresolved.map(a => a.display_name ?? "?")].join(", ")

  return (
    <Tooltip content={names}>
      <div className="avatar avatar-placeholder block rounded-full">
        <div className="w-8 h-8 rounded-full flex items-center justify-center">
          <span className="material-symbols-outlined text-sm">group</span>
          <span className="text-xs">{total}</span>
        </div>
      </div>
    </Tooltip>
  )
}
