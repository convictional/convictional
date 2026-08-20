import type { ChannelSubscription, WebSocketMessage, SubscriptionMessage } from "../types/channels"
import { ChannelMessageType } from "../types/channels"
import { topicKeyFromMessage } from "./topic"

/**
 * Reconstruct the wire form for a (re)subscribe from the topic's `topic_stream`/`topic_params`.
 */
function subscriptionFrame(
  subscription: ChannelSubscription,
  type: ChannelMessageType.SUBSCRIBE | ChannelMessageType.UNSUBSCRIBE
): SubscriptionMessage {
  if (!subscription.stream) {
    throw new Error(`ChannelSubscription '${subscription.name}' has no stream`)
  }
  return {
    type,
    topic_stream: subscription.stream,
    topic_params: subscription.topicParams,
    params: subscription.params,
  }
}

export class ChannelSubscriptionManager {
  // Keyed by the canonical topic name so both subscribe forms dedup and route together.
  private subscriptions = new Map<string, Set<ChannelSubscription>>()
  private confirmedSubscriptions = new Set<string>()

  add(subscription: ChannelSubscription): boolean {
    const { name } = subscription
    const isNewTopic = !this.subscriptions.has(name)

    if (isNewTopic) {
      this.subscriptions.set(name, new Set())
    }
    this.subscriptions.get(name)!.add(subscription)

    return isNewTopic
  }

  remove(subscription: ChannelSubscription): boolean {
    const topicSubscriptions = this.subscriptions.get(subscription.name)
    if (topicSubscriptions) {
      topicSubscriptions.delete(subscription)
      if (topicSubscriptions.size === 0) {
        this.subscriptions.delete(subscription.name)
        this.confirmedSubscriptions.delete(subscription.name)
        return true
      }
    }
    return false
  }

  getAllSubscriptions(): ChannelSubscription[] {
    const allSubscriptions: ChannelSubscription[] = []
    for (const subscriptions of this.subscriptions.values()) {
      allSubscriptions.push(...subscriptions)
    }
    return allSubscriptions
  }

  clear(): void {
    this.subscriptions.clear()
    this.confirmedSubscriptions.clear()
  }

  isConfirmed(name: string): boolean {
    return this.confirmedSubscriptions.has(name)
  }

  resubscribeAll(): SubscriptionMessage[] {
    this.confirmedSubscriptions.clear()
    const framesByName = new Map<string, SubscriptionMessage>()
    this.getAllSubscriptions().forEach(subscription => {
      if (!framesByName.has(subscription.name)) {
        framesByName.set(subscription.name, subscriptionFrame(subscription, ChannelMessageType.SUBSCRIBE))
      }
    })
    return Array.from(framesByName.values())
  }

  handleMessage(message: WebSocketMessage): void {
    const name = topicKeyFromMessage(message)
    if (!name) return

    if (message.type === ChannelMessageType.SUBSCRIPTION_CONFIRMED) {
      if (this.subscriptions.has(name)) {
        this.confirmedSubscriptions.add(name)
      }
    } else if (message.type === ChannelMessageType.SUBSCRIPTION_REJECTED) {
      this.subscriptions.delete(name)
      this.confirmedSubscriptions.delete(name)
    }

    this.handleBroadcast(message, name)
  }

  handleBroadcast(message: WebSocketMessage, name?: string): void {
    const topicName = name ?? topicKeyFromMessage(message)
    if (!topicName) return

    const subscriptions = this.subscriptions.get(topicName)
    if (subscriptions) {
      subscriptions.forEach(subscription => {
        try {
          subscription.callback(message)
        } catch {
          // Ignore callback errors
        }
      })
    }
  }
}
