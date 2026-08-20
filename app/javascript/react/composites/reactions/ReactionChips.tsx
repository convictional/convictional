import type { HTMLAttributes } from "react"

import { REACTION_EMOJI, type ReactionType } from "~/react/shared/reactions"
import type { ReactionUser } from "~/react/shared/types"
import { Tooltip } from "~/react/ui/Tooltip"

import { withScrollPreserved } from "./scrollUtils"

interface ReactionChipsProps {
  reactions: Record<string, ReactionUser[]>
  currentUserId: string | null
  onToggle: (reactionType: ReactionType) => void
  // Extra handlers spread onto each chip — e.g. the long-press handlers the
  // comment surfaces use to open the mobile reactor overlay.
  chipHandlers?: HTMLAttributes<HTMLButtonElement>
}

// One badge per active reaction: emoji + count, highlighted when the current
// user has reacted, with a tooltip listing reactors. The single chip-strip
// implementation shared by chat, posts, and comment surfaces.
export function ReactionChips({ reactions, currentUserId, onToggle, chipHandlers }: ReactionChipsProps) {
  return (
    <>
      {Object.entries(reactions).map(([type, users]) => {
        if (users.length === 0) return null
        const emoji = REACTION_EMOJI[type]
        if (!emoji) return null
        const isOwn = users.some(u => u.id === currentUserId)
        const names = users.map(u => (u.id === currentUserId ? "You" : u.display_name)).join(", ")
        return (
          <Tooltip key={type} content={names} placement="bottom">
            <button
              type="button"
              onMouseDown={e => e.preventDefault()}
              onPointerDown={e => e.preventDefault()}
              onClick={() => withScrollPreserved(() => onToggle(type as ReactionType))}
              className={`btn btn-sm rounded-full select-none touch-callout-none @mobile:min-h-8 ${isOwn ? "btn-primary" : ""}`}
              {...chipHandlers}
            >
              <span className="-mb-0.25">{emoji}</span>
              <span className={`font-semibold ${isOwn ? "text-primary" : "text-base-600"}`}>{users.length}</span>
            </button>
          </Tooltip>
        )
      })}
    </>
  )
}
