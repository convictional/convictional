// Find the id of the current user's most recent own item (message or comment)
// for Slack-style "press Up in an empty composer to edit your last one". The
// reverse-walk relies on the list being in chronological order. Accessor
// functions keep it shape-agnostic across item types whose user field is either
// required or nullable.
export function lastOwnItemId<T>(
  items: readonly T[],
  currentUserId: string | null,
  getUserId: (item: T) => string | null | undefined,
  getId: (item: T) => string
): string | null {
  if (!currentUserId) return null
  for (let i = items.length - 1; i >= 0; i--) {
    if (getUserId(items[i]) === currentUserId) return getId(items[i])
  }
  return null
}
