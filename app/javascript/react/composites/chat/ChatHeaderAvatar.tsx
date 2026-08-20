import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import type { ChatCollaborator, ChatType } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"
import { AvatarGroup } from "../AvatarGroup"

interface ChatHeaderAvatarProps {
  type: ChatType
  collaborators: ChatCollaborator[]
  currentUserId: string | null
  size?: "small" | "medium"
}

export function ChatHeaderAvatar({ type, collaborators, currentUserId, size = "small" }: ChatHeaderAvatarProps) {
  const isMobile = useIsMobile()
  const dim = size === "small" ? "w-6 h-6" : "w-8 h-8"

  if (type === "group") {
    return (
      <div className={`${dim} rounded-full bg-base-300 flex items-center justify-center`}>
        <span className="material-symbols-outlined text-sm text-base-content/50">group</span>
      </div>
    )
  }
  if (type === "self") {
    return (
      <div className={`${dim} rounded-full bg-base-300 flex items-center justify-center`}>
        <span className="material-symbols-outlined text-sm text-base-content/50">edit_note</span>
      </div>
    )
  }
  if (type === "multi") {
    // One avatar plus a "+N" chip on mobile so the notification header row fits.
    return <AvatarGroup users={collaborators.map(c => c.user)} size={size} layout="stack" max={isMobile ? 1 : 2} />
  }
  const other = collaborators.find(c => c.user.id !== currentUserId)
  if (!other) return <div className={`${dim} rounded-full bg-neutral-300`} />
  return <Avatar displayName={other.user.display_name} picture={other.user.picture} size={size} />
}
