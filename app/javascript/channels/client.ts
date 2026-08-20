import { ObservableV2 } from "lib0/observable"
import {
  ChannelMessageType,
  type ChannelStream,
  type ChannelSubscription,
  type WebSocketMessage,
  type ChannelParams,
} from "../types/channels"
import { type ChannelsBackend } from "./backends/base"
import { SharedConnectionBackend } from "./backends/sharedConnection"
import { ChannelSubscriptionManager } from "./subscriptionManager"
import { stringifyParams, Topic } from "./topic"

interface ChannelsClientEvents {
  connected: () => void
  disconnected: () => void
  reconnected: () => void
}

// A broadcast payload is any channel message minus its topic identity — the caller names the
// topic via (stream, params) and broadcastTo fills in topic_stream/topic_params. Distributes
// over the union so each message type keeps its own fields (e.g. is_typing, data).
type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never
type BroadcastPayload = DistributiveOmit<WebSocketMessage, "topic_stream" | "topic_params">

export class ChannelsClient extends ObservableV2<ChannelsClientEvents> {
  private subscriptionManager = new ChannelSubscriptionManager()
  private backend: ChannelsBackend
  private hasConnectedBefore = false

  constructor(backend?: ChannelsBackend) {
    super()
    this.backend = backend || new SharedConnectionBackend()
    this.setupEventHandlers()
  }

  async connect(): Promise<void> {
    return this.backend.connect()
  }

  /**
   * Subscribe by topic (React islands). The client names the topic from IDs it already
   * holds — no signed token round-trip. `params` form the topic identity (the canonical
   * `Topic.name`); `extraParams` ride in the server's SubscribeMessage.params and are not
   * part of the dedup key.
   */
  subscribeTo(
    stream: string,
    params: ChannelParams = {},
    callback: (data: WebSocketMessage) => void,
    extraParams: ChannelParams = {}
  ): ChannelSubscription {
    const topicParams = stringifyParams(params)
    const name = new Topic(stream, topicParams).name
    const subscription: ChannelSubscription = {
      name,
      stream,
      topicParams,
      params: extraParams,
      callback,
    }

    const isNewTopic = this.subscriptionManager.add(subscription)

    if (isNewTopic) {
      this.backend.send({
        type: ChannelMessageType.SUBSCRIBE,
        topic_stream: stream,
        topic_params: topicParams,
        params: extraParams,
      })
    } else if (this.subscriptionManager.isConfirmed(name)) {
      // Synthesize a confirmation for the already-confirmed topic; subscribers correlate by name.
      callback({
        type: ChannelMessageType.SUBSCRIPTION_CONFIRMED,
        topic_stream: stream,
        topic_params: topicParams,
      })
    }
    return subscription
  }

  unsubscribe(subscription: ChannelSubscription): void {
    const topicEmpty = this.subscriptionManager.remove(subscription)

    if (topicEmpty && subscription.stream) {
      this.backend.send({
        type: ChannelMessageType.UNSUBSCRIBE,
        topic_stream: subscription.stream,
        topic_params: subscription.topicParams,
      })
    }
  }

  /**
   * Broadcast a message to a topic named by (stream, params) — mirrors `subscribeTo`. The topic
   * identity must match what subscribers used (the server routes by the canonical topic name), so
   * naming it the same way here keeps broadcast and subscribe identity-consistent by construction.
   */
  broadcastTo(stream: ChannelStream, params: ChannelParams, payload: BroadcastPayload): void {
    this.backend.send({
      ...payload,
      topic_stream: stream,
      topic_params: stringifyParams(params),
    } as WebSocketMessage)
  }

  getConnectionState(): boolean {
    return this.backend.getConnectionState()
  }

  private resubscribeAll(): void {
    const messages = this.subscriptionManager.resubscribeAll()
    messages.forEach(message => {
      this.backend.send(message)
    })
  }

  private setupEventHandlers(): void {
    this.backend.on("connected", () => {
      if (this.hasConnectedBefore) {
        this.emit("reconnected", [])
      } else {
        this.hasConnectedBefore = true
      }
      this.emit("connected", [])
      this.resubscribeAll()
    })

    this.backend.on("disconnected", () => {
      this.emit("disconnected", [])
    })

    this.backend.on("message", message => {
      this.subscriptionManager.handleMessage(message)
    })
  }

  disconnect(): void {
    this.backend.disconnect()
  }
}

let instance: ChannelsClient | null = null

export function setChannelsClient(client: ChannelsClient): void {
  instance = client
}

export function getChannelsClient(): ChannelsClient | null {
  return instance
}
