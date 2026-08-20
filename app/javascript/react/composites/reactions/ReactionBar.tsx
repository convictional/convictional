import type { HTMLAttributes } from "react"

import { hasAnyReactions } from "~/react/shared/reactions"
import type { ReactionUser } from "~/react/shared/types"

import { ReactionChips } from "./ReactionChips"
import { ReactionMenu } from "./ReactionMenu"

interface ReactionBarProps {
  reactions: Record<string, ReactionUser[]>
  currentUserId: string
  onToggle: (reactionType: string) => void
  // Chat hides the whole bar until a reaction exists — its add-reaction
  // affordance lives in the hover MessageActions menu instead. Posts and other
  // surfaces keep the inline menu always visible since it's the only entry point.
  hideWhenEmpty?: boolean
  // Spread onto each chip — posts pass the long-press handlers here so pressing a
  // reaction opens the mobile action sheet (the touch stand-in for the tooltip).
  chipHandlers?: HTMLAttributes<HTMLButtonElement>
  // Posts hide the inline add-reaction menu on mobile, where adding a reaction
  // moves into the long-press action sheet (mirroring chat). The chips stay.
  showMenu?: boolean
  className?: string
}

// The shared "add-reaction menu + a badge per active reaction" strip, used by
// post and comment surfaces. Composes the shared ReactionMenu (picker) and
// ReactionChips (badges).
//
// Defaults to `contents` so the menu and chips join the caller's flex-wrap row
// as flat siblings alongside the DecisionMarker — otherwise the whole strip is
// one flex child that can't fit next to the marker and gets stranded on its own
// line. Callers that don't lay this out in a flex-wrap row pass a className.
export function ReactionBar({
  reactions,
  currentUserId,
  onToggle,
  hideWhenEmpty = false,
  chipHandlers,
  showMenu = true,
  className = "contents",
}: ReactionBarProps) {
  if (hideWhenEmpty && !hasAnyReactions(reactions)) return null

  return (
    <div className={className}>
      {showMenu && <ReactionMenu onSelect={onToggle} />}
      <ReactionChips
        reactions={reactions}
        currentUserId={currentUserId}
        onToggle={onToggle}
        chipHandlers={chipHandlers}
      />
    </div>
  )
}
