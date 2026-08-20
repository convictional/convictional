import { GroupPill } from "~/react/composites/MemberBadges"
import { UserAvatar } from "~/react/composites/UserAvatar"
import { Tooltip } from "~/react/ui/Tooltip"

import type { OrganizationUser } from "../types"
import { UserActions } from "./UserActions"

interface UserRowProps {
  user: OrganizationUser
  currentUserId: string | null
  onUpdated: (user: OrganizationUser) => void
}

// List row for a member — actions reveal on hover.
export function UserRow({ user, currentUserId, onUpdated }: UserRowProps) {
  const isCurrentUser = user.id === currentUserId

  return (
    <div
      id={`user-row-${user.id}`}
      className="w-full px-4 py-3 flex items-center justify-between bg-base-50 hover:bg-base-200 group border-b border-base-300 last:border-b-0"
    >
      <div className="flex items-center gap-2">
        <UserAvatar user={user} size="medium" />
        <div className="text-base flex items-center gap-2">
          <span className="text-sm">{user.display_name}</span>
          {user.is_admin && (
            <Tooltip content={`${user.display_name} is an admin`}>
              <span className="material-symbols-outlined text-sm text-base-content/70">shield</span>
            </Tooltip>
          )}
          {isCurrentUser && <span className="text-sm text-base-content/70">(you)</span>}
          {user.groups.map(group => (
            <GroupPill key={group.id} name={group.name} />
          ))}
        </div>
      </div>
      <div className="opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity flex items-center gap-4">
        <UserActions user={user} currentUserId={currentUserId} onUpdated={onUpdated} />
      </div>
    </div>
  )
}
