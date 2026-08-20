import { hashKey, type QueryKey, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef } from "react"

import { useReconnectInvalidate } from "~/react/shared/hooks/useReconnectInvalidate"

// Recover channel broadcasts a subscription missed while it was unwired. Two paths:
//   - socket reconnect  → useReconnectInvalidate (the channels client's "reconnected")
//   - warm remount      → the effect below (SPA navigation re-mounts an island while
//     the QueryClient singleton and socket survive; staleTime: Infinity means the
//     remount won't refetch on its own).
// A warm cache at mount means a prior mount fetched it, so invalidate to catch up. An
// errored entry is re-fetched too: channelQueryDefaults sets retryOnMount:false, so
// without this a transient first-load failure would stick across a remount with no
// recovery path until a socket reconnect. A cold first mount has no cached data yet
// (the query is still fetching), so it's skipped — which also makes this StrictMode-safe
// (both passes see a cold cache).
//
// Only for queries whose broadcasts REPLACE state (a plain refetch is correct). Do
// NOT use for queries that must MERGE a page-1 refetch to preserve pages 2+ or
// locally-mutated rows — see useGoalsData / useMailboxEntries.
export function useReconnectCatchUp(queryKey: QueryKey, label: string): void {
  const queryClient = useQueryClient()
  useReconnectInvalidate(queryKey, label)

  // Read the key through an always-current ref (as useReconnectInvalidate does) so a
  // caller passing a freshly-built array each render doesn't re-fire this effect;
  // hashKey is the stable change signal.
  const keyRef = useRef(queryKey)
  useEffect(() => {
    keyRef.current = queryKey
  })
  const keyHash = hashKey(queryKey)
  useEffect(() => {
    // Depends on the always-current ref update above running first (React executes
    // effects in declaration order), so keyRef.current is current when this fires.
    const state = queryClient.getQueryState(keyRef.current)
    if (state && (state.data !== undefined || state.status === "error")) {
      void queryClient.invalidateQueries({ queryKey: keyRef.current })
    }
  }, [queryClient, keyHash])
}
