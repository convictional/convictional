import type { User } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"

interface TypingIndicatorProps {
  users: User[]
}

export function TypingIndicator({ users }: TypingIndicatorProps) {
  if (users.length === 0) return null

  const visible = users.slice(0, 3)

  return (
    <div className="space-y-2 px-2">
      {visible.map(user => (
        <div key={user.id} className="flex gap-2 items-center">
          <Avatar picture={user.picture} displayName={user.display_name} size="medium" />
          <div className="bg-base-200 rounded-xl">
            <div className="p-3 flex gap-1 items-center">
              <div className="w-1.5 h-1.5 rounded-full bg-base-500 animate-[pulse_2s_infinite_250ms]" />
              <div className="w-1.5 h-1.5 rounded-full bg-base-500 animate-[pulse_2s_infinite_500ms]" />
              <div className="w-1.5 h-1.5 rounded-full bg-base-500 animate-[pulse_2s_infinite_750ms]" />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
