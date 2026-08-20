import { queryOptions } from "@tanstack/react-query"
import { createStore } from "zustand/vanilla"

import { type ChannelsClient, getChannelsClient } from "~/channels/client"
import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults, queryClient } from "~/react/shared/queryClient"

export type CurrentUser = {
  id: string
  display_name: string
  email: string
  is_superuser: boolean
  picture: string | null
  // Bootstrap fields the AppShell renders the authenticated chrome from (see
  // CurrentUserResponse in app/routers/api/schemas.py).
  is_admin: boolean
  organization_id: string
  organization_name: string | null
  time_zone: string | null
  feedback_upload_url: string
}

export type ClientConfig = {
  klipy_api_key: string | null
}

// Server flashes pending in the session at SPA boot. They ride along in the
// bootstrap payload because the SPA shell has no Jinja flash container; the
// AppShell drains them into the toaster once via consumeFlashes().
export type ServerFlash = {
  content: string
  level: string
}

export type CurrentUserApiResponse = CurrentUser & { client_config: ClientConfig; flashes: ServerFlash[] }

// What the cache holds under ["currentUser"]: user identity plus client_config.
// Flashes are deliberately excluded — they're one-shot ephemeral state that
// stays in Zustand below, not server state to cache.
export type CurrentUserData = {
  user: CurrentUser
  clientConfig: ClientConfig
}

// The queryFn seeds this store as a side effect; consumeFlashes drains it.
const flashesStore = createStore<{ flashes: ServerFlash[] }>(() => ({ flashes: [] }))

async function fetchCurrentUser({ signal }: { signal?: AbortSignal } = {}): Promise<CurrentUserData> {
  // Forward Query's abort signal so a refetch superseded by a newer one
  // (cancelRefetch) is actually cancelled at the network layer rather than
  // completing and still counting against the per-IP rate limiter.
  const {
    client_config: clientConfig,
    flashes,
    ...user
  } = await apiFetch<CurrentUserApiResponse>("/api/users/me", { signal })
  // Seed the flashes store as a side effect; flashes never enter the cache. Also
  // fires on reconnect/refresh refetches, not just bootstrap — server returns [].
  flashesStore.setState({ flashes: flashes ?? [] })
  return { user, clientConfig }
}

// queryOptions() brands the queryKey with the queryFn's data type, so getQueryData
// (peekCurrentUser) and setQueryData (test fixtures) are type-checked against
// CurrentUserData without a hand-written generic. Other callers reuse the key off it.
// currentUser is channel-backed (the store's single "reconnected" invalidate via
// armCurrentUserLiveUpdates), so it takes the channel-first posture.
export const currentUserQueryOptions = queryOptions({
  ...channelQueryDefaults,
  queryKey: ["currentUser"] as const,
  queryFn: fetchCurrentUser,
})

export const currentUserQueryKey = currentUserQueryOptions.queryKey

// Imperative accessor for non-React callers (shellBootstrap's beforeLoad). dedup
// and cache-hit are built into ensureQueryData, replacing the hand-rolled
// inFlight promise the Zustand store carried.
export function getCurrentUser(): Promise<CurrentUser> {
  return queryClient.ensureQueryData(currentUserQueryOptions).then(data => data.user)
}

// A refresh means "the identity payload may be stale" (a reconnect after the
// socket was down). Bursts are routine: a flaky or multi-tab socket emits several
// "reconnected" events in quick succession. invalidateQueries' default
// cancelRefetch:true fires a fresh refetch per call, so a burst would send one
// request per event and trip the per-IP rate limiter (429) — the failure mode
// that flooded /api/users/me. Coalesce here: keep at most one refetch in flight,
// plus a single trailing refetch for events that arrived while it ran, so a burst
// converges on the latest server state with one request, not one per event.
let refreshInFlight = false
let refreshQueued = false

export async function refreshCurrentUser(): Promise<void> {
  if (refreshInFlight) {
    refreshQueued = true
    return
  }
  refreshInFlight = true
  try {
    await queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
  } finally {
    refreshInFlight = false
    if (refreshQueued) {
      refreshQueued = false
      // Match onReconnect's posture; harmless even though invalidateQueries
      // never rejects today (query-core swallows refetch errors internally).
      void refreshCurrentUser().catch(() => {})
    }
  }
}

// The reconnect refetch is wired once per channels client, not once per
// useCurrentUser consumer. currentUser is read in ~40 places; a per-consumer
// "reconnected" listener meant a single reconnect fanned out to ~40 invalidations,
// each an uncancellable refetch — the multiplier behind the 429 storm. Arm a
// single listener instead, mirroring organizationMembers.
let liveClient: ChannelsClient | null = null

function onReconnect(): void {
  // The identity payload may have changed while the socket was down; re-warm it.
  // The network may still be settling on reconnect (common on mobile Safari), so
  // swallow transient fetch errors — apiFetch already reports, and an unhandled
  // rejection would surface a spurious Sentry event (regression: DECIDE-94W).
  void refreshCurrentUser().catch(() => {})
}

// Idempotent: safe to call from every useCurrentUser mount. No-ops once wired to
// the current client (and retries on a later call if the client wasn't ready yet,
// since the guard only latches a non-null client). Deliberately has NO unsubscribe
// counterpart on the hook side — a session-lifetime listener keeps currentUser
// fresh no matter how many islands read it, the same posture as org members.
export function armCurrentUserLiveUpdates(): void {
  const client = getChannelsClient()
  if (!client || client === liveClient) return
  liveClient = client
  client.on("reconnected", onReconnect)
}

// Tears down the reconnect wiring. The listener is intentionally session-lifetime
// (the hook arms without an unmount cleanup), so this exists only for tests to
// reset the singleton between cases; it has no production callers.
export function stopCurrentUserLiveUpdates(): void {
  liveClient?.off("reconnected", onReconnect)
  liveClient = null
  refreshInFlight = false
  refreshQueued = false
}

// Synchronous, non-reactive read of the cached user for callers that just need
// the current identity at call time (not a subscription) — e.g. UserHoverCard
// comparing a profile to the viewer. Returns undefined until the query resolves.
export function peekCurrentUser(): CurrentUser | undefined {
  return queryClient.getQueryData(currentUserQueryKey)?.user
}

// Returns the pending server flashes and clears them so they show only once.
// The AppShell calls this on mount to drain bootstrap flashes into the toaster.
export function consumeFlashes(): ServerFlash[] {
  const { flashes } = flashesStore.getState()
  if (flashes.length > 0) {
    flashesStore.setState({ flashes: [] })
  }
  return flashes
}
