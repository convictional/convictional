import type { User } from "~/react/shared/types"
import { Avatar, type AvatarBorder, type AvatarSize } from "~/react/ui/Avatar"

import { UserHoverCard } from "./UserHoverCard"

interface UserAvatarProps {
  user: User
  size?: AvatarSize
  isActive?: boolean
  border?: AvatarBorder
  // Wrap the avatar in a profile hover card. On by default — knowing which user
  // the avatar belongs to is the whole reason to reach for UserAvatar over the
  // bare ui/Avatar primitive. Opt out for surfaces that show a face but no card
  // (presence dots, picker rows) to render just the image.
  withHoverCard?: boolean
}

// The composite pairing of ui/Avatar with UserHoverCard. ui/Avatar stays a pure
// presentational primitive (no userId, no API calls); the card lives here where
// composites are allowed to fetch. AvatarGroup renders one of these per user.
export function UserAvatar({ user, size, isActive, border, withHoverCard = true }: UserAvatarProps) {
  const avatar = (
    <Avatar displayName={user.display_name} picture={user.picture} size={size} isActive={isActive} border={border} />
  )
  if (!withHoverCard) return avatar
  return <UserHoverCard userId={user.id}>{avatar}</UserHoverCard>
}
