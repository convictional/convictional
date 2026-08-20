import type { ChatCollaborator } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"

export function SlideView({
  visible,
  offset,
  children,
}: {
  visible: boolean
  // Where this view sits when NOT the active one. "left" = off to the left
  // (already navigated past), "right" = off to the right (not yet reached).
  offset: "left" | "right"
  children: React.ReactNode
}) {
  const translateX = visible ? "0%" : offset === "left" ? "-100%" : "100%"
  // Inline styles (not Tailwind classes) because Tailwind's JIT wasn't
  // picking up the translate/position utilities from this file — probably
  // a watcher cache issue. Inline removes that class of problem entirely.
  return (
    <div
      aria-hidden={!visible}
      inert={!visible}
      style={{
        position: "absolute",
        inset: 0,
        overflowY: "auto",
        transform: `translateX(${translateX})`,
        transition: "transform 300ms ease-out",
      }}
    >
      {children}
    </div>
  )
}

export function CollaboratorRow({
  collaborator,
  action,
}: {
  collaborator: ChatCollaborator
  action?: React.ReactNode
}) {
  return (
    <li className="group flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-base-200">
      <Avatar displayName={collaborator.user.display_name} picture={collaborator.user.picture} size="small" />
      <span className="flex-1 min-w-0 text-sm truncate">{collaborator.user.display_name}</span>
      {action}
    </li>
  )
}
