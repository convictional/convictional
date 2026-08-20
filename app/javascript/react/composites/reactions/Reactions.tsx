import { useCallback, useEffect, useState } from "react"

import { useLongPress } from "~/react/shared/hooks/useLongPress"
import { hasAnyReactions, REACTION_EMOJI, type ReactionType } from "~/react/shared/reactions"
import type { ReactionUser } from "~/react/shared/types"

import { ReactionChips } from "./ReactionChips"
import { ReactionMenu } from "./ReactionMenu"

interface ReactionsProps {
  reactions: Record<string, ReactionUser[]>
  currentUserId: string | null
  onToggle: (reactionType: ReactionType) => void
  // Surfaces that don't want the add-reaction trigger gated behind hover set this;
  // otherwise the trigger hover-reveals on desktop until the comment has reactions.
  alwaysShowAddButton?: boolean
}

// Chip strip + emoji picker + long-press reactor overlay. Pure data in, a single
// onToggle action out — no store dependency, so any comment surface can drive it.
// The chip strip and picker are the shared `ReactionChips`/`ReactionMenu`
// primitives; this component adds the comment-surface affordances (add-reaction
// trigger, mobile reactor overlay) on top.
export function Reactions({ reactions, currentUserId, onToggle, alwaysShowAddButton = false }: ReactionsProps) {
  const [showReactorOverlay, setShowReactorOverlay] = useState(false)
  const handleLongPress = useCallback(() => setShowReactorOverlay(true), [])
  const { handlers: longPressHandlers } = useLongPress(handleLongPress)

  useEffect(() => {
    if (!showReactorOverlay) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowReactorOverlay(false)
    }
    window.addEventListener("keydown", handler)
    // Lock background scroll while the overlay is open. We can't rely on
    // preventDefault in the backdrop's touch handlers — React registers
    // touchstart/touchmove as passive listeners, so preventDefault is ignored.
    document.body.classList.add("overflow-hidden")
    return () => {
      window.removeEventListener("keydown", handler)
      document.body.classList.remove("overflow-hidden")
    }
  }, [showReactorOverlay])

  const hasReactions = hasAnyReactions(reactions)

  return (
    <div className="flex items-center gap-1 mt-1 flex-wrap">
      <ReactionChips
        reactions={reactions}
        currentUserId={currentUserId}
        onToggle={onToggle}
        chipHandlers={longPressHandlers}
      />
      <ReactionMenu
        onSelect={onToggle}
        commentPortal
        trigger={
          <button
            type="button"
            aria-label="Add reaction"
            className={`cursor-pointer ${hasReactions || alwaysShowAddButton ? "" : "md:opacity-0 md:group-hover:opacity-100"} transition-opacity`}
          >
            <span className="material-symbols-outlined text-lg hover:text-base-600">mood</span>
          </button>
        }
      />
      {showReactorOverlay && (
        <div className="sm:hidden">
          <div
            data-testid="reaction-overlay-backdrop"
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
            onClick={() => setShowReactorOverlay(false)}
          />
          <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            onClick={() => setShowReactorOverlay(false)}
          >
            <div
              className="bg-base-100 rounded-xl shadow-xl p-4 max-w-sm w-full max-h-[60vh] overflow-y-auto space-y-3"
              onClick={e => e.stopPropagation()}
            >
              {Object.entries(reactions).map(([type, users]) =>
                users.length > 0 ? (
                  <div key={type} className="flex items-start gap-3">
                    <span className="text-xl">{REACTION_EMOJI[type]}</span>
                    <span className="text-sm">{users.map(u => u.display_name).join(", ")}</span>
                  </div>
                ) : null
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
