export const GROUP_TIME_THRESHOLD_MS = 5 * 60 * 1000

// Structural shape so any message-like record can be grouped. The author is
// nullable (some records have no user), and a null on either side breaks grouping.
type Groupable = { user: { id: string } | null; created_at: string }

export function isContinuation(prev: Groupable | undefined, current: Groupable): boolean {
  if (!prev || !prev.user || !current.user) return false
  if (prev.user.id !== current.user.id) return false
  const gap = new Date(current.created_at).getTime() - new Date(prev.created_at).getTime()
  if (gap < 0) return false
  return gap <= GROUP_TIME_THRESHOLD_MS
}
