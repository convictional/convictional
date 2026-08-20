import { queryOptions } from "@tanstack/react-query"

import { type ChannelsClient, getChannelsClient } from "~/channels/client"
import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults, queryClient } from "~/react/shared/queryClient"
import { getCurrentUser } from "~/react/shared/stores/currentUser"
import type { Group, OrganizationMembersResponse, User } from "~/react/shared/types"
import {
  ChannelEventAction,
  ChannelEventResource,
  ChannelMessageType,
  ChannelStream,
  type ChannelSubscription,
  type EventMessage,
  type WebSocketMessage,
} from "~/types/channels"

export type OrganizationMembers = { users: User[]; groups: Group[] }

async function fetchOrganizationMembers(): Promise<OrganizationMembers> {
  const { users, groups } = await apiFetch<OrganizationMembersResponse>("/api/organization/members")
  return { users, groups }
}

// organizationMembers is a session-lifetime singleton kept live by the
// organization_members channel (armOrganizationMembersLiveUpdates below), so it
// takes the channel-first posture: never background-refetch, a channel handler
// invalidates instead. queryOptions() brands the key with OrganizationMembers so
// getQueryData/setQueryData are type-checked off it without a hand-written generic.
export const organizationMembersQueryOptions = queryOptions({
  ...channelQueryDefaults,
  queryKey: ["organizationMembers"] as const,
  queryFn: fetchOrganizationMembers,
})

export const organizationMembersQueryKey = organizationMembersQueryOptions.queryKey

// Imperative accessor for non-React callers. dedup and cache-hit are built into
// ensureQueryData, replacing the hand-rolled inFlight promise the Zustand store
// carried — Query collapses concurrent reads to one in-flight fetch.
export function getOrganizationMembers(): Promise<OrganizationMembers> {
  return queryClient.ensureQueryData(organizationMembersQueryOptions)
}

// A refresh means "the data may be stale" (a membership event, or a reconnect after
// membership changed while disconnected). Bursts are routine: a bulk membership change
// broadcasts many UPDATED events, and a flaky or multi-tab socket can emit several
// "reconnected" events in quick succession. invalidateQueries' default cancelRefetch:true
// fires a fresh refetch per call — and because fetchOrganizationMembers doesn't forward
// Query's abort signal to fetch(), the "cancelled" requests still hit the network. So a
// burst sends one uncancellable request per event and trips the /api/organization/members
// rate limiter (429). Coalesce here instead: keep at most one refetch in flight, plus a
// single trailing refetch for changes that arrived while it ran, so a burst still converges
// on the latest server state rather than a stale mid-burst snapshot — without one request
// per event.
let refreshInFlight = false
let refreshQueued = false

export async function refreshOrganizationMembers(): Promise<void> {
  if (refreshInFlight) {
    refreshQueued = true
    return
  }
  refreshInFlight = true
  try {
    await queryClient.invalidateQueries({ queryKey: organizationMembersQueryKey })
  } finally {
    refreshInFlight = false
    if (refreshQueued) {
      refreshQueued = false
      void refreshOrganizationMembers()
    }
  }
}

// Live updates are wired once per channels client, not per component. The query
// is a session-lifetime singleton, so a single channel subscription + reconnect
// handler keep it fresh no matter how many islands read it — mounting N consumers
// must not mean N subscriptions and N refetches per membership event.
let liveClient: ChannelsClient | null = null
let channelSubscription: ChannelSubscription | null = null

function onReconnect(): void {
  // Membership may have changed while the socket was down; re-warm the data.
  void refreshOrganizationMembers()
}

function onChannelMessage(message: WebSocketMessage): void {
  if (message.type !== ChannelMessageType.EVENT) return
  const event = message as EventMessage
  if (event.resource !== ChannelEventResource.ORGANIZATION_MEMBERS) return
  // Any membership change (user/group added, removed, or renamed) arrives as a
  // single UPDATED event; invalidate to refetch the full payload.
  if (event.action === ChannelEventAction.UPDATED) {
    void refreshOrganizationMembers()
  }
}

// Idempotent: safe to call from every useOrganizationMembers mount. No-ops once
// wired to the current client (and retries on a later call if the client wasn't
// ready yet, since the guard only latches a non-null client). Deliberately has NO
// unsubscribe counterpart on the hook side: a per-mount subscription would drop
// on every navigation and re-arm on return, dragging org members into the
// cross-navigation staleness/catch-up regime. Wiring it once per session is
// exactly what keeps org members immune to navigation churn
// (see docs/react-migration.md → "Subscription re-arm → catch-up").
export function armOrganizationMembersLiveUpdates(): void {
  const client = getChannelsClient()
  if (!client || client === liveClient) return
  liveClient = client

  client.on("reconnected", onReconnect)

  // organization_id rides the current-user bootstrap; subscribe once it resolves.
  // Guard against a stop() (or a newer client latching) during the await window.
  void getCurrentUser()
    .then(user => {
      if (liveClient !== client || channelSubscription) return
      channelSubscription = client.subscribeTo(
        ChannelStream.ORGANIZATION_MEMBERS,
        { organization_id: user.organization_id },
        onChannelMessage
      )
    })
    .catch(() => {
      // apiFetch already reports the failure. Without a subscription the query still
      // refetches on reconnect; the next mount retries arming.
    })
}

// Tears down the live wiring. The subscription is intentionally session-lifetime
// (the hook arms without an unmount cleanup), so this exists only for tests to
// reset the singleton between cases; it has no production callers.
export function stopOrganizationMembersLiveUpdates(): void {
  if (liveClient && channelSubscription) liveClient.unsubscribe(channelSubscription)
  liveClient?.off("reconnected", onReconnect)
  channelSubscription = null
  liveClient = null
  refreshInFlight = false
  refreshQueued = false
}
