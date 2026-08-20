import type { Stores } from "alpinejs"
import type { ChannelsClient } from "./client"

// Alpine-accessible handle to the singleton channels client. Subscribe/unsubscribe/broadcast
// all go through `client` directly (see client.ts) — this store only exposes the client to
// Alpine components and the React `useChannelsClient` bridge.
export interface ChannelsStore extends Stores {
  client: ChannelsClient
}

export function createChannelsStore(channelsClient: ChannelsClient): ChannelsStore {
  return { client: channelsClient } as ChannelsStore
}
