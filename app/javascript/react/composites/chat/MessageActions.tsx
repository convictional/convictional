import { flip, offset, shift } from "@floating-ui/react"
import { useState } from "react"

import { DecisionMarker } from "~/react/composites/DecisionMarker"
import { ReactionMenu } from "~/react/composites/reactions/ReactionMenu"
import { Dropdown } from "~/react/ui/Dropdown"

// Keep the menu out from under the composer, and let it flip above the
// message when the message sits near the bottom of the viewport.
const CHAT_MENU_MIDDLEWARE = [
  offset(4),
  flip({ fallbackPlacements: ["top-start"], padding: { bottom: 96 } }),
  shift({ padding: { top: 8, bottom: 96, left: 8, right: 8 } }),
]

interface MessageActionsProps {
  isOwn: boolean
  hasReactions: boolean
  isCompact?: boolean
  onReact: (reactionType: string) => void
  onReply: () => void
  onEdit: () => void
  onDelete: () => void
  // Present only when this island wired decisions (chatShow, not chatPanel). The
  // undecided "Decide" affordance lives here in the hover toolbar; the decided
  // pill renders in the always-visible footer beside reactions instead.
  onToggleDecision?: () => void
}

export function MessageActions({
  isOwn,
  hasReactions,
  isCompact,
  onReact,
  onReply,
  onEdit,
  onDelete,
  onToggleDecision,
}: MessageActionsProps) {
  const [showMenu, setShowMenu] = useState(false)

  return (
    <div
      className={`opacity-0 group-hover:opacity-100 transition-opacity hidden sm:flex items-center mt-1 ${
        isCompact ? "flex-col gap-0.5" : "gap-2"
      }`}
    >
      {onToggleDecision && <DecisionMarker decision={undefined} onToggle={onToggleDecision} />}
      {!hasReactions && <ReactionMenu onSelect={onReact} />}
      <button type="button" onClick={onReply} className="btn btn-sm btn-ghost btn-square" aria-label="Reply">
        <span className="material-symbols-outlined text-base">reply</span>
      </button>
      {isOwn && (
        <Dropdown
          placement="bottom-start"
          open={showMenu}
          onOpenChange={setShowMenu}
          closeOnGroupLeave
          middleware={CHAT_MENU_MIDDLEWARE}
          className="z-50 dropdown-card p-2 text-base-600"
          trigger={
            <button type="button" className="btn btn-sm btn-ghost btn-square">
              <span className="material-symbols-outlined text-base">more_horiz</span>
            </button>
          }
        >
          {({ close }) => (
            <ul>
              <li>
                <button
                  type="button"
                  onClick={() => {
                    close()
                    onEdit()
                  }}
                  className="dropdown-item"
                >
                  Edit
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => {
                    close()
                    onDelete()
                  }}
                  className="dropdown-item"
                >
                  Delete
                </button>
              </li>
            </ul>
          )}
        </Dropdown>
      )}
    </div>
  )
}
