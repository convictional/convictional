// One-line summary of an email thread's latest "activity" event for the inbox row. The server ships
// the raw EventAction + Event details (see EmailEntryDetail) rather than a phrased string, so the
// wording lives here. Cross-resource actions (collaborator add/remove, assignment, decided) are
// phrased by the shared describeCrossResourceActivity.

import {
  type ActivityContext,
  describeCrossResourceActivity,
} from "~/react/composites/mailboxPreview/crossResourceActivity"
import type { EventAction } from "~/react/shared/types"

type Details = Record<string, unknown>

// Draft schedule/unschedule is recorded as a workspace event so the row broadcasts and refreshes
// its scheduled badge, but it deliberately gets no preview line — the row keeps the draft's own
// snippet. Returning null tells the caller to fall back to that snippet.
const NON_PREVIEW_ACTIONS: ReadonlySet<EventAction> = new Set(["draft_scheduled", "draft_unscheduled"])

export function describeEmailActivity(
  action: EventAction | null,
  details: Details | null,
  context: ActivityContext = {}
): string | null {
  if (action && NON_PREVIEW_ACTIONS.has(action)) return null

  return describeCrossResourceActivity(action, details ?? {}, context) ?? "Updated this thread"
}
