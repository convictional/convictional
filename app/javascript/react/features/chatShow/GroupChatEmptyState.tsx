import { AvatarGroup } from "~/react/composites/AvatarGroup"
import { ResourceBadge } from "~/react/composites/ResourceBadge"
import type { ChatCollaborator } from "~/react/shared/types"
import { EmptyStateSurface } from "~/react/ui/EmptyStateSurface"
import { pluralize } from "~/shared/strings"

interface GroupChatEmptyStateProps {
  chatTitle: string
  // Solo = the current user is the only member. Drives the invite-first variant
  // (the first-run General chat), versus the say-hello variant when others are present.
  isSolo: boolean
  collaborators: ChatCollaborator[]
  currentUserId: string
  onAddPeople: () => void
  onStartMessage: () => void
}

function joinWithAnd(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ""
  if (items.length === 2) return `${items[0]} and ${items[1]}`
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`
}

function memberListLabel(collaborators: ChatCollaborator[], currentUserId: string): string {
  const others = collaborators.filter(c => c.user.id !== currentUserId).map(c => c.user.display_name.split(" ")[0])
  const shown = others.slice(0, 3)
  const remaining = others.length - shown.length
  const items = ["You", ...shown]
  if (remaining > 0) items.push(`${remaining} ${pluralize(remaining, "other")}`)
  return `${joinWithAnd(items)} are here`
}

export function GroupChatEmptyState({
  chatTitle,
  isSolo,
  collaborators,
  currentUserId,
  onAddPeople,
  onStartMessage,
}: GroupChatEmptyStateProps) {
  return (
    <EmptyStateSurface className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-4 rounded-2xl border border-base-300 bg-base-50 p-1 shadow-sm">
        <ResourceBadge contentType="chat" size="medium" />
      </div>

      <h2 className="max-w-sm font-accent text-lg text-base-content text-balance">
        Welcome to the start of {chatTitle}
      </h2>

      {isSolo ? (
        <div className="mt-3 text-xs font-medium text-base-content/60">You&rsquo;re the first one here</div>
      ) : (
        <div className="mt-3 flex items-center gap-2 text-xs text-base-content/60">
          <AvatarGroup users={collaborators.map(c => c.user)} layout="stack" size="small" max={5} />
          <span>{memberListLabel(collaborators, currentUserId)}</span>
        </div>
      )}

      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {isSolo ? (
          <>
            <button type="button" className="btn btn-primary" onClick={onAddPeople}>
              Invite your team
            </button>
            <button type="button" className="btn btn-ghost" onClick={onStartMessage}>
              Post a welcome message
            </button>
          </>
        ) : (
          <>
            <button type="button" className="btn btn-primary" onClick={onStartMessage}>
              Say hello
            </button>
            <button type="button" className="btn btn-ghost" onClick={onAddPeople}>
              Add people
            </button>
          </>
        )}
      </div>

      <ul className="mt-6 flex w-full max-w-sm flex-col gap-3 border-t border-base-300 pt-5 text-left">
        <li className="flex items-start gap-2.5 text-sm text-base-content/60">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-base-200 text-base-content/70">
            <span className="material-symbols-outlined leading-none" style={{ fontSize: "16px" }}>
              alternate_email
            </span>
          </span>
          <span className="text-pretty">
            <span className="font-medium text-base-content">@mention</span> anyone to pull them into a thread.
          </span>
        </li>
        <li className="flex items-start gap-2.5 text-sm text-base-content/60">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-base-200 text-base-content/70">
            <span className="material-symbols-outlined leading-none" style={{ fontSize: "16px" }}>
              alt_route
            </span>
          </span>
          <span className="text-pretty">
            Turn any message into a <span className="font-medium text-base-content">decision</span> your team can find
            later.
          </span>
        </li>
      </ul>
    </EmptyStateSurface>
  )
}
