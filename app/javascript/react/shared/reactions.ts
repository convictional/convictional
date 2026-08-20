import type { ReactionUser } from "~/react/shared/types"

// Mirrors COMMENT_REACTIONS in app/models/collaboration/workspace.py
export const REACTIONS = [
  { type: "thumbs_up", emoji: "👍", label: "thumbs up" },
  { type: "thumbs_down", emoji: "👎", label: "thumbs down" },
  { type: "tears_of_joy", emoji: "😂", label: "face with tears of joy" },
  { type: "party_popper", emoji: "🎉", label: "party popper" },
  { type: "frowning_face", emoji: "🙁", label: "slightly frowning face" },
  { type: "heart", emoji: "❤️", label: "red heart" },
  { type: "rocket", emoji: "🚀", label: "rocket" },
  { type: "eyes", emoji: "👀", label: "eyes" },
] as const

export type ReactionType = (typeof REACTIONS)[number]["type"]

export const REACTION_EMOJI: Record<string, string> = Object.fromEntries(REACTIONS.map(r => [r.type, r.emoji]))

// True when any reaction bucket holds at least one user. Kept generic over the
// bucket element so every comment/message surface shares one "has reactions" test.
export function hasAnyReactions(reactions: Record<string, readonly unknown[]>): boolean {
  return Object.values(reactions).some(users => users.length > 0)
}

// Returns a new map (never mutates the input) so callers can use it as React
// state. Toggling off the last user leaves an empty bucket, matching the map
// the server returns.
export function toggleReactionInMap(
  reactions: Record<string, ReactionUser[]>,
  reactionType: string,
  user: ReactionUser
): Record<string, ReactionUser[]> {
  const next = { ...reactions }
  const users = [...(next[reactionType] ?? [])]
  const idx = users.findIndex(u => u.id === user.id)
  if (idx >= 0) {
    users.splice(idx, 1)
  } else {
    users.push(user)
  }
  next[reactionType] = users
  return next
}
