import { AvatarGroup } from "~/react/composites/AvatarGroup"
import { Avatar } from "~/react/ui/Avatar"

import type { MeetingDetail } from "../types"

interface AttendeeListProps {
  userAttendees: MeetingDetail["user_attendees"]
  unresolvedAttendees: MeetingDetail["unresolved_attendees"]
}

// Resolved org users render through the shared AvatarGroup. Unresolved
// attendees aren't Users (no id / profile card), so they render as standalone
// placeholder avatars beside the group. Both stay in raw server order — no
// client-side RSVP re-sort.
export function AttendeeList({ userAttendees, unresolvedAttendees }: AttendeeListProps) {
  if (userAttendees.length === 0 && unresolvedAttendees.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-semibold text-base-500">Attendees</span>
      {userAttendees.length > 0 && (
        <AvatarGroup users={userAttendees} layout="stack" size="medium" max={userAttendees.length} withHoverCard />
      )}
      {unresolvedAttendees.map((attendee, index) => (
        <div
          key={`${attendee.display_name ?? "unknown"}-${index}`}
          className="tooltip"
          data-tip={attendee.display_name ?? "Unknown"}
        >
          <Avatar displayName={attendee.display_name ?? "?"} picture={null} size="medium" border="ring" />
        </div>
      ))}
    </div>
  )
}
