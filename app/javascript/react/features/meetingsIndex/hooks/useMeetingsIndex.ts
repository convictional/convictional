import { useCallback, useState } from "react"

import { apiFetch, ApiError, errorMessage } from "~/react/shared/apiFetch"
import { usePaginatedList } from "~/react/shared/hooks/usePaginatedList"
import type {
  MeetingCollectionListItem,
  MeetingCollectionShowResponse,
  MeetingListResponse,
  MeetingResponse,
} from "~/react/shared/types"

interface Args {
  collectionId: string | null
  uncategorized: boolean
}

// Collection mode keeps fetching the dedicated show endpoint, which bundles the
// `collection` metadata (for the editable header) alongside the page of
// meetings. Pseudo modes hit /api/meetings. Both produce the same meeting list
// (past, declined included, newest first), so the pagination and rendering paths
// downstream are identical — only the URL and response shape differ here.
function buildUrl({ collectionId, uncategorized }: Args, cursor: string | null): string {
  if (collectionId !== null) {
    const params = new URLSearchParams()
    if (cursor) params.set("cursor", cursor)
    const qs = params.toString()
    return `/api/meetings_collections/${collectionId}${qs ? `?${qs}` : ""}`
  }
  const params = new URLSearchParams()
  // `past` (not `completed`) and `include_declined` keep the list at parity with
  // the dedicated collection endpoint and the legacy /meetings page.
  params.set("past", "true")
  params.set("include_declined", "true")
  params.set("sort", "scheduled_at_desc")
  if (uncategorized) params.set("uncategorized", "true")
  if (cursor) params.set("cursor", cursor)
  return `/api/meetings?${params.toString()}`
}

export function useMeetingsIndex({ collectionId, uncategorized }: Args) {
  const [collection, setCollection] = useState<MeetingCollectionListItem | null>(null)

  const {
    items: meetings,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    setItems: setMeetings,
  } = usePaginatedList<MeetingResponse, MeetingCollectionShowResponse | MeetingListResponse>({
    buildUrl: cursor => buildUrl({ collectionId, uncategorized }, cursor),
    select: data => data.meetings,
    deps: [collectionId, uncategorized],
    // Only the collection show endpoint returns `collection`; the pseudo modes
    // hit /api/meetings and have none, so clear the header for those.
    onPage: data => setCollection("collection" in data ? data.collection : null),
  })

  const upsertMeeting = useCallback(
    (updated: MeetingResponse) => {
      // PATCH /api/meetings sends the meeting back with its (possibly new)
      // collection assignment. Drop the row when the new assignment no longer
      // belongs in the list being viewed, so the page reflects the move without
      // a refetch. "Most Recent" shows everything, so it never drops.
      let stillHere = true
      if (collectionId) stillHere = updated.collection?.id === collectionId
      else if (uncategorized) stillHere = updated.collection == null
      setMeetings(prev =>
        stillHere ? prev.map(m => (m.id === updated.id ? updated : m)) : prev.filter(m => m.id !== updated.id)
      )
    },
    [collectionId, uncategorized, setMeetings]
  )

  const updateCollection = useCallback(
    async (changes: { title?: string; description?: string | null }): Promise<string | null> => {
      if (!collectionId) return "No collection to update."
      try {
        const updated = await apiFetch<MeetingCollectionListItem>(`/api/meetings_collections/${collectionId}`, {
          method: "PATCH",
          body: JSON.stringify(changes),
        })
        setCollection(updated)
        return null
      } catch (e) {
        return errorMessage(e, "Failed to update collection.")
      }
    },
    [collectionId]
  )

  const deleteCollection = useCallback(async (): Promise<string | null> => {
    if (!collectionId) return "No collection to delete."
    try {
      await apiFetch(`/api/meetings_collections/${collectionId}`, { method: "DELETE" })
      return null
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const detail = typeof e.body?.detail === "string" ? e.body.detail : null
        return detail ?? "This collection can't be deleted."
      }
      return errorMessage(e, "Failed to delete collection.")
    }
  }, [collectionId])

  return {
    collection,
    meetings,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    upsertMeeting,
    updateCollection,
    deleteCollection,
  }
}
