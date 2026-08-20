import { useCallback } from "react"

import { apiFetch } from "~/react/shared/apiFetch"

/**
 * Visit recording is the frontend entry point for read state — "mark as seen" / "last viewed" /
 * unread / "what's new" on a workspace resource all flow from recording a Visit. Reuse this;
 * don't build a parallel read-state store.
 *
 * Fire-and-forget visit recorder. Returns a stable `recordVisit` that POSTs
 * `{last_event_id}` to the given visit endpoint. Pure transport: the caller owns
 * the endpoint and the "when" — postShow debounces a catch-up on new comments,
 * emailThreadShow/documents record once on load, goalShow once per timeline event.
 *
 * `url` may be null (the resource id hasn't loaded yet) — `recordVisit` no-ops
 * in that case, so callers don't each reinvent a guard.
 *
 * Most callers want `useWorkspaceVisitRecording`; this stays the extension point
 * for any future visit endpoint.
 */
export function useVisitRecording(url: string | null): (lastEventId?: string | null) => void {
  return useCallback(
    (lastEventId?: string | null) => {
      if (!url) return
      apiFetch(url, {
        method: "POST",
        body: JSON.stringify({ last_event_id: lastEventId ?? null }),
      }).catch(() => {})
    },
    [url]
  )
}

/**
 * Records a visit to a workspace — every resource (posts, email threads, documents,
 * goals) records through this one shared endpoint. Pass null while the workspace id is
 * still loading. The server broadcasts any resource-specific live view-state refresh
 * (e.g. a goal's "Seen by" timeline) off this write, so callers don't need a bespoke endpoint.
 */
export function useWorkspaceVisitRecording(workspaceId: string | null): (lastEventId?: string | null) => void {
  return useVisitRecording(workspaceId ? `/api/workspaces/${workspaceId}/visits` : null)
}
