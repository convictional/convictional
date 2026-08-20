import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"

import {
  armOrganizationMembersLiveUpdates,
  organizationMembersQueryOptions,
} from "~/react/shared/stores/organizationMembers"
import type { Group, User } from "~/react/shared/types"

type Result = {
  users: User[]
  groups: Group[]
  loading: boolean
  error: Error | null
}

export function useOrganizationMembers({ enabled = true }: { enabled?: boolean } = {}): Result {
  const { data, isLoading, error } = useQuery({ ...organizationMembersQueryOptions, enabled })

  useEffect(() => {
    // Arm the organization_members channel + reconnect refetch once per session.
    // The store's module-level guards keep N mounts to one subscription, and the
    // call deliberately returns no cleanup: a session-lifetime subscription prevents
    // staleness across navigation boundaries (see docs/react-migration.md).
    // Arming unconditionally (not gated on data) lets an errored query recover —
    // retryOnMount is off, so the channel/reconnect invalidate is its only path.
    if (!enabled) return
    armOrganizationMembersLiveUpdates()
  }, [enabled])

  // loading is true only on the first load with no data yet; Query keeps previous
  // data on screen during a channel/reconnect refetch, so there's no flash.
  return {
    users: data?.users ?? [],
    groups: data?.groups ?? [],
    loading: isLoading,
    error,
  }
}
