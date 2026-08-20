import type { ReactNode } from "react"

import type { User } from "~/react/shared/types"
import type { AvatarSize } from "~/react/ui/Avatar"
import { Tooltip } from "~/react/ui/Tooltip"
import { UserAvatar } from "./UserAvatar"

export type AvatarGroupLayout = "compact" | "stack"

interface AvatarGroupProps {
  users: User[]
  layout?: AvatarGroupLayout
  size?: AvatarSize
  max?: number
  presentUserIds?: string[]
  // Only meaningful when presentUserIds is set; sorts present users to the front.
  sortPresentFirst?: boolean
  // Passed through to each UserAvatar's hover card; defaults true for compact, false for stack.
  withHoverCard?: boolean
  // Rendered in place of the group when users is empty. Defaults to null.
  emptyState?: ReactNode
}

const COMPACT_OFFSET_PX = 8

// Overflow chip dimensions mirror Avatar's SIZE_CLASSES so the "+N" badge is the
// same size as the avatars it sits beside in a stack.
const STACK_OVERFLOW_CLASSES: Record<AvatarSize, string> = {
  xs: "w-4 h-4 text-[8px]",
  small: "w-5 h-5 text-[10px]",
  medium: "w-6 h-6 text-[11px]",
  large: "w-8 h-8 text-xs",
}

export function AvatarGroup({
  users,
  layout = "compact",
  size,
  max,
  presentUserIds,
  sortPresentFirst = false,
  withHoverCard,
  emptyState = null,
}: AvatarGroupProps) {
  if (users.length === 0) return <>{emptyState}</>

  const resolvedSize: AvatarSize = size ?? (layout === "compact" ? "xs" : "small")
  const resolvedMax = max ?? (layout === "compact" ? 2 : 5)
  const resolvedHoverCard = withHoverCard ?? layout === "compact"

  const presentIds = presentUserIds ? new Set(presentUserIds) : null
  const ordered =
    sortPresentFirst && presentIds
      ? [...users].sort((a, b) => Number(presentIds.has(b.id)) - Number(presentIds.has(a.id)))
      : users

  const shown = ordered.slice(0, resolvedMax)
  const overflow = ordered.slice(resolvedMax)

  const isActive = (user: User) => (presentIds ? presentIds.has(user.id) : false)

  if (layout === "compact") {
    return (
      <CompactLayout
        shown={shown}
        overflow={overflow}
        size={resolvedSize}
        isActive={isActive}
        withHoverCard={resolvedHoverCard}
      />
    )
  }
  return (
    <StackLayout
      shown={shown}
      overflow={overflow}
      size={resolvedSize}
      isActive={isActive}
      withHoverCard={resolvedHoverCard}
    />
  )
}

interface LayoutProps {
  shown: User[]
  overflow: User[]
  size: AvatarSize
  isActive: (user: User) => boolean
  withHoverCard: boolean
}

function CompactLayout({ shown, overflow, size, isActive, withHoverCard }: LayoutProps) {
  const count = shown.length + (overflow.length > 0 ? 1 : 0)
  // Each item overlaps the previous by 50% — width is (count * COMPACT_OFFSET_PX) since
  // the last item extends one avatar-width past the last left-offset (16px for xs).
  return (
    <div className="relative h-4" style={{ width: `${count * COMPACT_OFFSET_PX}px` }}>
      {shown.map((user, i) => (
        <div
          key={user.id}
          className="absolute top-1/2 -translate-y-1/2 ring-2 ring-base-100 rounded-full"
          style={{ left: `${i * COMPACT_OFFSET_PX}px`, zIndex: i }}
        >
          <UserAvatar
            user={user}
            size={size}
            isActive={isActive(user)}
            border="spacer"
            withHoverCard={withHoverCard}
          />
        </div>
      ))}
      {overflow.length > 0 && (
        <div
          className="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-base-300 flex items-center justify-center ring-2 ring-base-100 text-[9px] text-base-content/70 font-medium"
          style={{ left: `${shown.length * COMPACT_OFFSET_PX}px`, zIndex: shown.length }}
        >
          +{overflow.length}
        </div>
      )}
    </div>
  )
}

function StackLayout({ shown, overflow, size, isActive, withHoverCard }: LayoutProps) {
  return (
    <div className="avatar-group -space-x-2">
      {shown.map(user =>
        // Present users sort to the front, so the overlapping neighbor would clip
        // their info-content ring. A relative z-indexed span lifts them above it.
        isActive(user) ? (
          <span key={user.id} className="relative z-10">
            <UserAvatar user={user} size={size} isActive border="ring" withHoverCard={withHoverCard} />
          </span>
        ) : (
          <UserAvatar
            key={user.id}
            user={user}
            size={size}
            isActive={false}
            border="ring"
            withHoverCard={withHoverCard}
          />
        )
      )}
      {overflow.length > 0 && <StackOverflowChip overflow={overflow} size={size} />}
    </div>
  )
}

function StackOverflowChip({ overflow, size }: { overflow: User[]; size: AvatarSize }) {
  // Skip the `+` glyph beyond 10 to avoid overflowing the chip.
  const prefix = overflow.length <= 10 ? "+" : ""
  return (
    <Tooltip
      content={
        <ul className="space-y-1">
          {overflow.map(u => (
            <li key={u.id}>{u.display_name}</li>
          ))}
        </ul>
      }
    >
      <div className="avatar avatar-placeholder block rounded-full static border-3 border-base-100 font-semibold text-base-600">
        <div className={`${STACK_OVERFLOW_CLASSES[size]} rounded-full bg-base-200 flex items-center justify-center`}>
          <span>
            {prefix}
            {overflow.length}
          </span>
        </div>
      </div>
    </Tooltip>
  )
}
