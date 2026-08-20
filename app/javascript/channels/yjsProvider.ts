import * as buffer from "lib0/buffer"
import * as decoding from "lib0/decoding"
import * as encoding from "lib0/encoding"
import { ObservableV2 } from "lib0/observable"
import { Awareness, encodeAwarenessUpdate, applyAwarenessUpdate } from "y-protocols/awareness"
import { messageYjsSyncStep2, readSyncMessage, writeSyncStep1, writeUpdate } from "y-protocols/sync"
import * as Y from "yjs"

import {
  type ChannelStream,
  type ChannelSubscription,
  type WebSocketMessage,
  ChannelMessageType,
  type LiveDocumentSyncMessage,
  type LiveDocumentAwarenessMessage,
} from "../types/channels"
import { ChannelsClient } from "./client"

export class ChannelsYjsProvider extends ObservableV2<{
  status: (data: { status: "disconnected" | "connecting" | "connected" }) => void
}> {
  private ydoc: Y.Doc
  private stream: ChannelStream
  private params: Record<string, string>
  private channelsClient: ChannelsClient
  private subscription: ChannelSubscription | null = null
  private is_synced = false
  private resyncInterval: number | null = null
  private resyncIntervalMs: number
  private updateDebounceTimeout: ReturnType<typeof setTimeout> | null = null
  private pendingUpdates: Uint8Array[] = []
  private readonly updateDebounceMs: number = 150
  public awareness: Awareness
  private disconnectHandler: () => void
  private reconnectHandler: () => void

  constructor(
    channelsClient: ChannelsClient,
    stream: ChannelStream,
    params: Record<string, string>,
    ydoc: Y.Doc,
    options: { resyncInterval?: number } = {}
  ) {
    super()
    this.channelsClient = channelsClient
    this.stream = stream
    this.params = params
    this.ydoc = ydoc
    this.awareness = new Awareness(ydoc)
    this.resyncIntervalMs = options.resyncInterval || 30000

    this.disconnectHandler = () => this.handleDisconnect()
    this.reconnectHandler = () => this.handleReconnect()

    this.awareness.on(
      "update",
      ({ added, updated, removed }: { added: number[]; updated: number[]; removed: number[] }) => {
        const changedClients = added.concat(updated).concat(removed)
        const update = encodeAwarenessUpdate(this.awareness, changedClients)
        this.writeAwareness(update)
      }
    )
    this.ydoc.on("update", (update, origin) => {
      if (origin !== this) {
        this.debouncedUpdate(update)
      }
    })
    this.channelsClient.on("disconnected", this.disconnectHandler)
    this.channelsClient.on("reconnected", this.reconnectHandler)
    this.start()
  }

  private start(): void {
    if (this.subscription) {
      return
    }

    this.emit("status", [{ status: "connecting" }])

    this.subscription = this.channelsClient.subscribeTo(this.stream, this.params, (message: WebSocketMessage) => {
      if (message.type === ChannelMessageType.SUBSCRIPTION_CONFIRMED) {
        this.emit("status", [{ status: "connected" }])
        this.requestSync()
        this.startResyncInterval()
      } else if (message.type === ChannelMessageType.LIVE_DOCUMENT_SYNC) {
        this.handleSyncMessage(message)
      } else if (message.type === ChannelMessageType.LIVE_DOCUMENT_AWARENESS) {
        this.handleAwarenessMessage(message)
      }
    })
  }

  private handleSyncMessage(message: LiveDocumentSyncMessage): void {
    const bytes = buffer.fromBase64(message.data)
    const decoder = decoding.createDecoder(bytes)
    const encoder = encoding.createEncoder()

    const messageType = readSyncMessage(decoder, encoder, this.ydoc, this)
    if (messageType == messageYjsSyncStep2 && !this.is_synced) {
      this.is_synced = true
      this.ydoc.emit("sync", [this.is_synced, this.ydoc])
    }

    if (encoding.length(encoder) > 1) {
      this.writeSync(encoder)
    }
  }

  private handleAwarenessMessage(message: LiveDocumentAwarenessMessage): void {
    const bytes = buffer.fromBase64(message.data)

    applyAwarenessUpdate(this.awareness, bytes, this)
  }

  private debouncedUpdate(update: Uint8Array): void {
    this.pendingUpdates.push(update)

    if (this.updateDebounceTimeout) {
      clearTimeout(this.updateDebounceTimeout)
    }

    this.updateDebounceTimeout = setTimeout(() => {
      this.flushPendingUpdates()
    }, this.updateDebounceMs)
  }

  private flushPendingUpdates(): void {
    if (this.pendingUpdates.length === 0) return

    const mergedUpdate = Y.mergeUpdates(this.pendingUpdates)
    const encoder = encoding.createEncoder()
    writeUpdate(encoder, mergedUpdate)

    this.pendingUpdates = []
    this.updateDebounceTimeout = null
    this.writeSync(encoder)
  }

  private requestSync(): void {
    // Request sync by sending sync step 1
    const encoder = encoding.createEncoder()
    writeSyncStep1(encoder, this.ydoc)
    this.writeSync(encoder)
  }

  private writeSync(encoder: encoding.Encoder): void {
    const data = encoding.toUint8Array(encoder)
    this.channelsClient.broadcastTo(this.stream, this.params, {
      type: ChannelMessageType.LIVE_DOCUMENT_SYNC,
      data: buffer.toBase64(data),
      origin: "provider",
    })
  }

  private writeAwareness(awarenessUpdate: Uint8Array): void {
    this.channelsClient.broadcastTo(this.stream, this.params, {
      type: ChannelMessageType.LIVE_DOCUMENT_AWARENESS,
      data: buffer.toBase64(awarenessUpdate),
      origin: "provider",
    })
  }

  private startResyncInterval(): void {
    if (this.resyncInterval) {
      clearInterval(this.resyncInterval)
    }

    this.resyncInterval = window.setInterval(() => {
      this.requestSync()
    }, this.resyncIntervalMs)
  }

  private stopResyncInterval(): void {
    if (this.resyncInterval) {
      clearInterval(this.resyncInterval)
      this.resyncInterval = null
    }
  }

  private handleDisconnect(): void {
    this.is_synced = false
    this.stopResyncInterval()
    this.emit("status", [{ status: "disconnected" }])
  }

  private handleReconnect(): void {
    // Re-broadcast awareness so other users see us after reconnection
    const localState = this.awareness.getLocalState()
    if (localState !== null) {
      const update = encodeAwarenessUpdate(this.awareness, [this.ydoc.clientID])
      this.writeAwareness(update)
    }
  }

  destroy(): void {
    this.stopResyncInterval()

    if (this.updateDebounceTimeout) {
      clearTimeout(this.updateDebounceTimeout)
      this.flushPendingUpdates()
    }

    this.channelsClient.off("disconnected", this.disconnectHandler)
    this.channelsClient.off("reconnected", this.reconnectHandler)

    if (this.subscription) {
      this.channelsClient.unsubscribe(this.subscription)
      this.subscription = null
    }
    this.emit("status", [{ status: "disconnected" }])
    this.awareness.destroy()
  }
}
