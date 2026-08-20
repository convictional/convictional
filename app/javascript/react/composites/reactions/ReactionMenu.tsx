import { type Middleware, type Placement, flip, offset, shift } from "@floating-ui/react"
import { type ReactElement, useState } from "react"

import { REACTIONS, type ReactionType } from "~/react/shared/reactions"
import { Dropdown } from "~/react/ui/Dropdown"

import { withScrollPreserved } from "./scrollUtils"

// Keep the menu out from under the composer, and let it flip above the
// message when the message sits near the bottom of the viewport.
const REACTION_MENU_MIDDLEWARE: Middleware[] = [
  offset(4),
  flip({ fallbackPlacements: ["top-start"], padding: { bottom: 96 } }),
  shift({ padding: { top: 8, bottom: 96, left: 8, right: 8 } }),
]

interface ReactionMenuProps {
  onSelect: (reactionType: ReactionType) => void
  placement?: Placement
  // When true, the emoji panel is tagged `data-comment-portal` so picking an
  // emoji inside the editor's CommentSystem doesn't trip its click-outside and
  // dismiss the active comment. Harmless on surfaces with no CommentSystem.
  commentPortal?: boolean
  // Override the default "Add reaction" affordance. Comment surfaces pass a
  // hover-revealed mood icon; chat/posts use the default always-visible button.
  trigger?: ReactElement
}

const DEFAULT_TRIGGER = (
  <button
    type="button"
    onMouseDown={e => e.preventDefault()}
    onPointerDown={e => e.preventDefault()}
    className="btn btn-sm btn-ghost btn-square"
    aria-label="Add reaction"
  >
    <span className="material-symbols-outlined text-lg">mood</span>
  </button>
)

export function ReactionMenu({
  onSelect,
  placement = "bottom-start",
  commentPortal = false,
  trigger = DEFAULT_TRIGGER,
}: ReactionMenuProps) {
  const [isOpen, setIsOpen] = useState(false)

  // strategy: "fixed" anchors the floating element to the viewport via
  // `position: fixed` instead of `position: absolute`. Critical for the chat:
  // the FloatingPortal mounts the dropdown at body root, where an absolute
  // child's layout box sits at document (0, 0) regardless of where it's
  // visually drawn by the transform. Tapping an emoji focuses the button, and
  // browsers scroll to bring the focused button's layout box into view —
  // which lurches the page up by the full distance to body top. With
  // `position: fixed`, the layout box is anchored to the viewport, so
  // focus-driven auto-scroll does nothing.
  return (
    <Dropdown
      open={isOpen}
      onOpenChange={setIsOpen}
      placement={placement}
      strategy="fixed"
      closeOnGroupLeave
      middleware={REACTION_MENU_MIDDLEWARE}
      className="z-50 dropdown-card p-2 flex"
      // Don't bounce focus back to the trigger on close: after a mouse pick that
      // leaves WebKit painting a focus ring on the "Add reaction" button.
      returnFocus={false}
      trigger={trigger}
    >
      {({ close }) => (
        <ul className="flex" {...(commentPortal ? { "data-comment-portal": true } : {})}>
          {REACTIONS.map(r => (
            <li key={r.type}>
              <button
                type="button"
                onMouseDown={e => e.preventDefault()}
                onPointerDown={e => e.preventDefault()}
                className="dropdown-item text-xs aspect-square w-8 flex items-center justify-center"
                onClick={() =>
                  withScrollPreserved(() => {
                    onSelect(r.type)
                    close()
                  })
                }
              >
                <span role="img" aria-label={r.label}>
                  {r.emoji}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Dropdown>
  )
}
