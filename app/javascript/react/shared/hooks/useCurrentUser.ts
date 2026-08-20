import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"

import {
  armCurrentUserLiveUpdates,
  type ClientConfig,
  type CurrentUser,
  currentUserQueryOptions,
} from "~/react/shared/stores/currentUser"

type Result = {
  user: CurrentUser | null
  clientConfig: ClientConfig | null
  loading: boolean
  error: Error | null
}

export function useCurrentUser(): Result {
  const { data, isLoading, error } = useQuery(currentUserQueryOptions)

  useEffect(() => {
    // Arm the reconnect refetch once per session. The store's module-level guard
    // collapses all consumers to a single "reconnected" listener, so a reconnect
    // fires one /api/users/me request rather than one per consumer.
    armCurrentUserLiveUpdates()
  }, [])

  return { user: data?.user ?? null, clientConfig: data?.clientConfig ?? null, loading: isLoading, error }
}
