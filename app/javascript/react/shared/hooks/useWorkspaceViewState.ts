import { useEffect, useMemo, useState } from "react"

import { useWorkspaceCollaboratorsQuery } from "~/react/shared/hooks/useWorkspaceCollaboratorsQuery"
import type { User } from "~/react/shared/types"

export interface WorkspaceViewState {
  // The current user's read cursor as of page arrival — anchors the "New activity" divider. Frozen on
  // first load: the user's own visit records as the page loads (racing this read), so we capture the
  // arrival cursor once and ignore later advances, keeping the divider stable and correct. Callers must
  // gate visit recording on `ready` so this first read predates the visit (see goalShow useVisitRecording).
  lastSeenEventId: string | null
  // event_id -> other viewers whose cursor sits at that event ("Seen by" avatars).
  readersByEventId: Map<string, User[]>
  // True once the collaborators query has loaded and the arrival cursor is captured.
  ready: boolean
}

// Derived "Seen by" / last-seen state for a workspace, built from the shared, channel-live collaborators
// query (view_state per viewer) rather than any resource's timeline response — so a recorded visit
// anywhere updates it without re-fetching. Not goal-specific; usable by any collaboratable resource.
export function useWorkspaceViewState(workspaceId: string, currentUserId: string): WorkspaceViewState {
  const { data } = useWorkspaceCollaboratorsQuery(workspaceId)

  // Freeze the arrival cursor at the first loaded value; undefined until then. Captured in an effect so
  // later refetches (e.g. triggered by another viewer's visit, which advances our own cursor server-side)
  // can't move the divider mid-session.
  const [arrivalCursor, setArrivalCursor] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    if (data && arrivalCursor === undefined) {
      setArrivalCursor(data.current_user_view_state.last_viewed_event_id ?? null)
    }
  }, [data, arrivalCursor])

  const readersByEventId = useMemo(() => {
    const map = new Map<string, User[]>()

    // Collaborators plus non-collaborator viewers — both carry {user, view_state}. Deriving from
    // collaborators alone would drop org members who viewed an org-shared goal (see WorkspaceViewer).
    for (const reader of [...(data?.collaborators ?? []), ...(data?.viewers ?? [])]) {
      if (reader.user.id === currentUserId) continue
      const eventId = reader.view_state.last_viewed_event_id
      if (!eventId) continue
      const readers = map.get(eventId)
      if (readers) readers.push(reader.user)
      else map.set(eventId, [reader.user])
    }

    return map
  }, [data, currentUserId])

  return { lastSeenEventId: arrivalCursor ?? null, readersByEventId, ready: data !== undefined }
}
