import { AvatarGroup } from "~/react/composites/AvatarGroup"
import type { User } from "~/react/shared/types"

interface SeenByAvatarsProps {
  readers: User[]
}

export function SeenByAvatars({ readers }: SeenByAvatarsProps) {
  if (readers.length === 0) return null

  return (
    <div
      className="flex justify-start items-center gap-1 mt-1"
      title={`Seen by ${readers.map(u => u.display_name).join(", ")}`}
    >
      <span className="material-symbols-outlined text-sm text-base-content/30 cursor-default translate-y-px">
        visibility
      </span>
      <AvatarGroup users={readers} />
    </div>
  )
}
