import { afterEach, beforeEach, describe, expect, it } from "vitest"
import * as Y from "yjs"

import { ChannelsClient } from "../../../app/javascript/channels/client"
import { ChannelsYjsProvider } from "../../../app/javascript/channels/yjsProvider"
import { ChannelMessageType, type WebSocketMessage } from "../../../app/javascript/types/channels"

// Records what the provider sends so we can assert it subscribes/broadcasts by the
// unsigned topic (stream + params), never the signed topic_id, and re-announces
// awareness on reconnect — the resync-after-drop path the migration must preserve.
class FakeChannelsClient {
  subscribeToCalls: Array<{ stream: string; params: Record<string, string> }> = []
  broadcasts: WebSocketMessage[] = []
  private callback: ((message: WebSocketMessage) => void) | null = null
  private reconnectHandlers = new Set<() => void>()
  private disconnectHandlers = new Set<() => void>()

  subscribeTo(stream: string, params: Record<string, string>, callback: (message: WebSocketMessage) => void) {
    this.subscribeToCalls.push({ stream, params })
    this.callback = callback
    return { name: `${stream}` }
  }

  unsubscribe() {
    this.callback = null
  }

  broadcastTo(stream: string, params: Record<string, string>, payload: Record<string, unknown>) {
    this.broadcasts.push({ ...payload, topic_stream: stream, topic_params: params } as WebSocketMessage)
  }

  on(event: string, cb: () => void) {
    if (event === "reconnected") this.reconnectHandlers.add(cb)
    if (event === "disconnected") this.disconnectHandlers.add(cb)
  }

  off(event: string, cb: () => void) {
    this.reconnectHandlers.delete(cb)
    this.disconnectHandlers.delete(cb)
  }

  deliver(message: WebSocketMessage) {
    this.callback?.(message)
  }

  emitReconnect() {
    this.reconnectHandlers.forEach(h => h())
  }
}

describe("ChannelsYjsProvider unsigned subscribe", () => {
  let client: FakeChannelsClient
  let ydoc: Y.Doc
  let provider: ChannelsYjsProvider

  beforeEach(() => {
    client = new FakeChannelsClient()
    ydoc = new Y.Doc()
    provider = new ChannelsYjsProvider(client as unknown as ChannelsClient, "document", { document_id: "doc-1" }, ydoc)
  })

  afterEach(() => {
    provider.destroy()
    ydoc.destroy()
  })

  it("subscribes to the unsigned stream + params", () => {
    expect(client.subscribeToCalls).toEqual([{ stream: "document", params: { document_id: "doc-1" } }])
  })

  it("broadcasts sync frames with topic_stream/topic_params and no topic_id", () => {
    // SUBSCRIPTION_CONFIRMED triggers the initial sync request (writeSync).
    client.deliver({ type: ChannelMessageType.SUBSCRIPTION_CONFIRMED } as WebSocketMessage)
    const sync = client.broadcasts.find(m => m.type === ChannelMessageType.LIVE_DOCUMENT_SYNC)
    expect(sync).toBeDefined()
    expect(sync?.topic_stream).toBe("document")
    expect(sync?.topic_params).toEqual({ document_id: "doc-1" })
    expect(sync?.topic_id).toBeUndefined()
  })

  it("broadcasts awareness with the unsigned topic", () => {
    provider.awareness.setLocalStateField("user", { id: "u1", name: "Tester" })
    const awareness = client.broadcasts.find(m => m.type === ChannelMessageType.LIVE_DOCUMENT_AWARENESS)
    expect(awareness?.topic_stream).toBe("document")
    expect(awareness?.topic_params).toEqual({ document_id: "doc-1" })
    expect(awareness?.topic_id).toBeUndefined()
  })

  it("re-announces awareness on reconnect so cursors recover after a drop", () => {
    provider.awareness.setLocalStateField("user", { id: "u1", name: "Tester" })
    client.broadcasts.length = 0
    client.emitReconnect()
    const reAnnounced = client.broadcasts.find(m => m.type === ChannelMessageType.LIVE_DOCUMENT_AWARENESS)
    expect(reAnnounced?.topic_stream).toBe("document")
    expect(reAnnounced?.topic_params).toEqual({ document_id: "doc-1" })
  })
})
