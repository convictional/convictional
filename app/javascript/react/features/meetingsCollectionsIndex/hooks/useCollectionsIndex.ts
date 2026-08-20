import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch, errorMessage } from "~/react/shared/apiFetch"
import { fetchAllCollections } from "~/react/shared/collections"
import type { MeetingCollectionListItem } from "~/react/shared/types"

export function useCollectionsIndex() {
  const [collections, setCollections] = useState<MeetingCollectionListItem[]>([])
  const [uncategorizedCount, setUncategorizedCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const requestIdRef = useRef(0)

  const refresh = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    // Guard every state write so a superseded refresh can't clobber a newer
    // one's results — matches the dedup pattern in the paginated hooks.
    const thisRequest = ++requestIdRef.current
    setLoading(true)
    try {
      const result = await fetchAllCollections(controller.signal)
      if (requestIdRef.current !== thisRequest) return
      setCollections(result.collections)
      setUncategorizedCount(result.uncategorizedCount)
      setError(false)
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return
      if (requestIdRef.current === thisRequest) setError(true)
    } finally {
      if (requestIdRef.current === thisRequest) setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    return () => abortRef.current?.abort()
  }, [refresh])

  const create = useCallback(async (title: string, description: string | null): Promise<string | null> => {
    try {
      const created = await apiFetch<MeetingCollectionListItem>("/api/meetings_collections", {
        method: "POST",
        body: JSON.stringify({
          title,
          ...(description ? { description } : {}),
        }),
      })
      setCollections(prev => [...prev, created].sort((a, b) => a.title.localeCompare(b.title)))
      return null
    } catch (e) {
      return errorMessage(e, "Failed to create collection.")
    }
  }, [])

  return { collections, uncategorizedCount, loading, error, refresh, create }
}
