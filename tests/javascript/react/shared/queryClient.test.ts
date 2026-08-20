import { describe, expect, test } from "vitest"

import { channelQueryDefaults, queryClient } from "~/react/shared/queryClient"

describe("queryClient", () => {
  test("the only client-wide default is retry: false (apiFetch owns Sentry + 401)", () => {
    const queries = queryClient.getDefaultOptions().queries
    expect(queries?.retry).toBe(false)
    // The channel-first posture is per-query, not global, so non-channel reads
    // keep TanStack's defaults and still recover on remount.
    expect(queries?.staleTime).toBeUndefined()
    expect(queries?.refetchOnMount).toBeUndefined()
    expect(queries?.retryOnMount).toBeUndefined()
  })

  test("channelQueryDefaults is channel-first: no background refetch, no remount retry", () => {
    expect(channelQueryDefaults.staleTime).toBe(Infinity)
    expect(channelQueryDefaults.refetchOnMount).toBe(false)
    // retryOnMount: false is the property that stops an errored query from
    // re-hitting the network on every observer remount (the refetch loop).
    expect(channelQueryDefaults.retryOnMount).toBe(false)
    expect(channelQueryDefaults.refetchOnWindowFocus).toBe(false)
    expect(channelQueryDefaults.refetchOnReconnect).toBe(false)
  })
})
