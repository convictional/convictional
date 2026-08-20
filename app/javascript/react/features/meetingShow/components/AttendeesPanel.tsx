import { AvatarGroup } from "~/react/composites/AvatarGroup"
import { Avatar } from "~/react/ui/Avatar"
import { Tooltip } from "~/react/ui/Tooltip"

import type { AttendeeStatus, UserAttendee } from "../types"

interface AttendeesPanelProps {
  resolved: UserAttendee[]
  unresolved: AttendeeStatus[]
}

// Resolved org users render through the shared AvatarGroup (name + hover profile
// card). Unresolved attendees aren't Users — no id, no profile — so they render
// as standalone placeholder avatars with a plain name tooltip. The list is
// uncapped (max = length) so every attendee renders on the show page.
export function AttendeesPanel({ resolved, unresolved }: AttendeesPanelProps) {
  if (resolved.length === 0 && unresolved.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-1 py-2">
      {resolved.length > 0 && (
        <AvatarGroup users={resolved} layout="stack" size="small" max={resolved.length} withHoverCard />
      )}
      {unresolved.map((attendee, index) => {
        const label = attendee.display_name ?? "?"
        return (
          <Tooltip key={`unresolved-${index}`} content={label} placement="bottom">
            <Avatar displayName={label} picture={null} size="small" border="ring" />
          </Tooltip>
        )
      })}
    </div>
  )
}
