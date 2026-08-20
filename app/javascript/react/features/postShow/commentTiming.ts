// Matches `CommentMixin.was_edited` on the server: an edit is meaningful only
// when updated_at drifts more than 10s past created_at (the initial save bumps
// updated_at by a sub-second amount). The API doesn't send a `was_edited`
// boolean; the client derives it from the two timestamps.
const EDIT_THRESHOLD_MS = 10_000

export function wasEdited(createdAt: string, updatedAt: string): boolean {
  return Date.parse(updatedAt) - Date.parse(createdAt) > EDIT_THRESHOLD_MS
}
