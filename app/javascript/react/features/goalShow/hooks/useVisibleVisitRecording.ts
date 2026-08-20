import { useEffect, useRef } from "react"

import { useWorkspaceVisitRecording } from "~/react/shared/hooks/useVisitRecording"

// Records the workspace Visit read-cursor up to `newestEventId`, but only while the tab is visible,
// so a backgrounded goal tab receiving live events doesn't silently advance the cursor and mark
// activity the user never looked at as seen. On return-to-visible it catches up to the newest event.
// Each event id records at most once (dedupes visibility toggles and StrictMode double-mounts); each
// real advance still POSTs, which broadcasts the live "Seen by" update to other viewers.
//
// Gate on `ready` so the arrival cursor (the "New activity" divider anchor) is frozen before the
// first advance — see useWorkspaceViewState.
export function useVisibleVisitRecording(workspaceId: string, newestEventId: string | null, ready: boolean): void {
  const recordVisit = useWorkspaceVisitRecording(workspaceId)
  const recordedEventIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (!ready || !newestEventId) return

    const recordIfVisible = () => {
      if (document.visibilityState !== "visible") return
      if (recordedEventIdRef.current === newestEventId) return
      recordedEventIdRef.current = newestEventId
      recordVisit(newestEventId)
    }

    recordIfVisible()
    document.addEventListener("visibilitychange", recordIfVisible)
    return () => document.removeEventListener("visibilitychange", recordIfVisible)
  }, [ready, newestEventId, recordVisit])
}
