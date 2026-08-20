import { openDirectMessagePanel } from "~/react/shared/openChatPanel"
import { Avatar } from "~/react/ui/Avatar"
import { Skeleton } from "~/react/ui/Skeleton"
import { GoalBadge } from "./goals/GoalBadge"
import { AdminBadge, GroupPill } from "./MemberBadges"

export interface ProfileCardUser {
  id: string
  display_name: string
  picture: string | null
  email: string
  bio: string | null
  is_admin: boolean
}

export interface ProfileCardGoal {
  id: string
  title: string | null
  description: string
  parent: { description: string } | null
}

export interface ProfileCardData {
  user: ProfileCardUser
  isCurrentUser: boolean
  groups: { id: string; name: string }[]
  goal: ProfileCardGoal | null
}

export function ProfileCardSkeleton() {
  return (
    <div className="dropdown-card w-72 p-4">
      <div className="flex items-center gap-3">
        <Skeleton className="h-10 w-10 shrink-0 rounded-full" />
        <div className="space-y-1.5 flex-1">
          <Skeleton className="h-3 w-3/4" />
          <Skeleton className="h-2.5 w-1/2" />
        </div>
      </div>
    </div>
  )
}

export function ProfileCard({ data }: { data: ProfileCardData }) {
  const { user, groups, goal, isCurrentUser } = data

  return (
    <div className="dropdown-card w-72 p-4 flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <Avatar displayName={user.display_name} picture={user.picture} size="large" />
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="text-sm font-semibold truncate">{user.display_name}</p>
            {isCurrentUser && <span className="text-xs text-base-content/50">(you)</span>}
          </div>
          <p className="text-xs text-base-content/50 truncate">{user.email}</p>
        </div>
      </div>
      <div className="border-t border-base-200 -mx-4" />
      {user.bio && <p className="text-xs text-base-content/70 line-clamp-3">{user.bio}</p>}
      {goal && (
        <div className="flex items-center gap-2 min-w-0 overflow-hidden">
          <div className="flex-1 min-w-0">
            <GoalBadge goal={goal} theme="beige" size="small" />
          </div>
        </div>
      )}
      <div className="flex items-center justify-between -mb-2 mt-auto">
        <div className="flex items-center gap-2 flex-wrap">
          {user.is_admin && <AdminBadge />}
          {groups.map(group => (
            <GroupPill key={group.id} name={group.name} />
          ))}
        </div>
        <div className="flex items-center gap-2">
          <a
            href={`/organization/users#user-${user.id}`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center text-base-content/40 hover:text-base-content/70 shrink-0"
          >
            <span className="material-symbols-outlined text-lg">open_in_new</span>
          </a>
        </div>
      </div>
      {!isCurrentUser && (
        <button type="button" onClick={() => openDirectMessagePanel(user)} className="btn w-full cursor-pointer">
          Direct message
        </button>
      )}
    </div>
  )
}
