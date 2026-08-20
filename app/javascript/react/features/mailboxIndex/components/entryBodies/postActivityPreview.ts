import {
  type ActivityContext,
  describeCrossResourceActivity,
} from "~/react/composites/mailboxPreview/crossResourceActivity"
import type { EventAction } from "~/react/shared/types"

type Details = Record<string, unknown>

// post_created / post_announced are fallbacks: the server maps those to preview_kind "comment"
// whenever the post has an original_comment (see mailbox_entries.py), so they only reach here for
// the rare comment-less post.
const ACTIVITY_MESSAGES: Partial<Record<EventAction, string>> = {
  post_created: "Posted",
  post_announced: "Announced",
  post_pinned: "Pinned this post",
}

export function describePostActivity(
  action: EventAction | null,
  details: Details | null,
  context: ActivityContext = {}
): string {
  const shared = describeCrossResourceActivity(action, details ?? {}, context)
  if (shared) return shared
  return (action && ACTIVITY_MESSAGES[action]) || "Updated this post"
}
