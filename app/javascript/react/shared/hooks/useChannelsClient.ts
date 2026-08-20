import { useMemo } from "react"

import { ChannelsClient, getChannelsClient } from "~/channels/client"

// Resolve the singleton ChannelsClient. Both boot paths register it via
// setChannelsClient — main.ts for legacy pages, the AppShell route for the SPA
// (which never creates the Alpine store) — so the module singleton is the
// source of truth. The Alpine store is a fallback for any legacy page that
// somehow lacks the module registration; on legacy pages both hold the same
// instance.
export function useChannelsClient(): ChannelsClient | null {
  return useMemo(() => {
    const fromModule = getChannelsClient()
    if (fromModule) return fromModule

    const alpine = window.Alpine as unknown as
      { store: (name: string) => { client: ChannelsClient } | undefined } | undefined
    const client = alpine?.store("channels")?.client ?? null
    if (!client) console.warn("useChannelsClient: channels client not available at mount time")
    return client
  }, [])
}
