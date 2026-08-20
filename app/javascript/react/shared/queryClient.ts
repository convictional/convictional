import { QueryClient } from "@tanstack/react-query"

// One module-level client shared by every React root (islands, the SPA), the way
// the Zustand singletons and ChannelsClient are shared. A per-root client would
// fragment the cache: currentUser fetched N times, channel patches not crossing
// islands. See docs/react-migration.md → "Server state with TanStack Query".
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The only client-wide default. apiFetch already reports to Sentry and owns
      // the 401 redirect, so a Query retry would double-report and fight that
      // redirect — true for every query, channel-backed or not. The channel-first
      // posture (staleTime, refetch/retry-on-mount) is deliberately NOT global:
      // it lives in channelQueryDefaults so non-channel reads keep TanStack's
      // defaults and still recover on remount.
      retry: false,
    },
  },
})

// The channel-first posture for server state kept live by a WebSocket channel.
// The channel is the freshness AND recovery source, so a channel-backed query
// never background-refetches and never re-hits the network for an errored query
// on remount — a channel handler invalidates instead (reconnect/re-arm, or an
// explicit user action). Without this, a query gated on its own error state
// remounts observers into a refetch loop. Spread into a query's queryOptions;
// non-channel-backed reads omit it and recover on remount like normal queries.
export const channelQueryDefaults = {
  // Never stale enough to background-refetch; a channel handler invalidates it.
  staleTime: Infinity,
  // A new observer mounting never refetches cached data (refetchOnMount) and
  // never re-hits the network for an errored, data-less query (retryOnMount,
  // true by default). The first observer of a cold query still fetches.
  refetchOnMount: false,
  retryOnMount: false,
  refetchOnWindowFocus: false,
  // Reconnect freshness rides the channels client's "reconnected" event (a real
  // socket reconnect), not the browser online event, which fires on flaky
  // transitions the socket hasn't acted on yet.
  refetchOnReconnect: false,
} as const
