import { type QueryKey, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef } from "react"

import { getChannelsClient } from "~/channels/client"

// Refetch a channel-backed query when the socket reconnects. channelQueryDefaults
// disables refetchOnReconnect, so broadcasts missed while the socket was down are
// recovered here by invalidating on the channels client's "reconnected" event.
// The network may still be settling on reconnect (common on mobile Safari), so
// transient fetch errors are swallowed — an unhandled rejection would surface a
// spurious Sentry event. `label` only tags that warning.
//
// queryKey is read through a ref (the always-current ref pattern, as in useChannel)
// so callers can pass a freshly-built array each render without re-subscribing.
export function useReconnectInvalidate(queryKey: QueryKey, label: string): void {
  const queryClient = useQueryClient()
  const keyRef = useRef(queryKey)
  // No dependency array (the always-current ref pattern, as in useChannel): keep
  // the ref pointed at the latest queryKey without re-running the subscribe effect.
  useEffect(() => {
    keyRef.current = queryKey
  })

  useEffect(() => {
    const client = getChannelsClient()
    if (!client) return
    const onReconnect = () => {
      void queryClient.invalidateQueries({ queryKey: keyRef.current }).catch((err: unknown) => {
        console.warn(`${label}: refresh failed after reconnect`, err)
      })
    }
    client.on("reconnected", onReconnect)
    return () => client.off("reconnected", onReconnect)
  }, [queryClient, label])
}
