import { expect, test, beforeEach, vi } from "vitest"
import { ChannelSubscriptionManager } from "../../../app/javascript/channels/subscriptionManager"
import { ChannelMessageType } from "../../../app/javascript/types/channels"
import type { ChannelSubscription, EventMessage } from "../../../app/javascript/types/channels"

let subscriptionManager: ChannelSubscriptionManager

beforeEach(() => {
  subscriptionManager = new ChannelSubscriptionManager()
})

// A stream-only unsigned subscription whose canonical name is the stream itself.
function subscription(stream: string, callback: () => void, params?: Record<string, string>): ChannelSubscription {
  return { name: stream, stream, topicParams: {}, callback, params }
}

// A topic-carrying message addressed to a stream-only topic.
function eventMessage(stream: string): EventMessage {
  return {
    type: ChannelMessageType.EVENT,
    topic_stream: stream,
    topic_params: {},
    resource: "goal_timeline" as never,
    action: "updated" as never,
    data: {},
  }
}

test("subscription manager handles broadcast messages to all callbacks on a topic", () => {
  const callback1 = vi.fn()
  const callback2 = vi.fn()
  subscriptionManager.add(subscription("test-topic", callback1))
  subscriptionManager.add(subscription("test-topic", callback2))

  const message = eventMessage("test-topic")

  subscriptionManager.handleBroadcast(message)

  expect(callback1).toHaveBeenCalledWith(message)
  expect(callback2).toHaveBeenCalledWith(message)
})

test("subscription manager routes unsigned (stream) subscriptions by canonical name", () => {
  const callback = vi.fn()
  const other = vi.fn()
  // Two subscriptions to different topics that share a stream — only matching params should fire.
  subscriptionManager.add({
    name: "goal_timeline:goal_id:5",
    stream: "goal_timeline",
    topicParams: { goal_id: "5" },
    callback,
  })
  subscriptionManager.add({
    name: "goal_timeline:goal_id:9",
    stream: "goal_timeline",
    topicParams: { goal_id: "9" },
    callback: other,
  })

  const message = {
    type: ChannelMessageType.EVENT,
    topic_stream: "goal_timeline",
    topic_params: { goal_id: "5" },
    resource: "goal_timeline",
    action: "updated",
    data: {},
  } as never

  subscriptionManager.handleBroadcast(message)

  expect(callback).toHaveBeenCalledWith(message)
  expect(other).not.toHaveBeenCalled()
})

test("subscription manager maintains separate subscriptions for different topics", () => {
  const callback1 = vi.fn()
  const callback2 = vi.fn()
  subscriptionManager.add(subscription("topic1", callback1))
  subscriptionManager.add(subscription("topic2", callback2))

  const message1 = eventMessage("topic1")
  const message2 = eventMessage("topic2")

  subscriptionManager.handleBroadcast(message1)
  subscriptionManager.handleBroadcast(message2)

  expect(callback1).toHaveBeenCalledWith(message1)
  expect(callback1).not.toHaveBeenCalledWith(message2)
  expect(callback2).toHaveBeenCalledWith(message2)
  expect(callback2).not.toHaveBeenCalledWith(message1)
})

test("subscription reuse lifecycle: creation to confirmation keys by name", () => {
  const callback1 = vi.fn()
  const callback2 = vi.fn()
  const callback3 = vi.fn()

  expect(subscriptionManager.add(subscription("test-topic", callback1))).toBe(true)
  expect(subscriptionManager.isConfirmed("test-topic")).toBe(false)

  // Second subscription before confirmation reuses the topic.
  expect(subscriptionManager.add(subscription("test-topic", callback2))).toBe(false)
  expect(subscriptionManager.isConfirmed("test-topic")).toBe(false)

  subscriptionManager.handleMessage({
    type: ChannelMessageType.SUBSCRIPTION_CONFIRMED,
    topic_stream: "test-topic",
    topic_params: {},
  })

  expect(subscriptionManager.isConfirmed("test-topic")).toBe(true)
  expect(callback1).toHaveBeenCalled()
  expect(callback2).toHaveBeenCalled()

  // Third subscription after confirmation still reuses.
  expect(subscriptionManager.add(subscription("test-topic", callback3))).toBe(false)
  expect(subscriptionManager.isConfirmed("test-topic")).toBe(true)
})

test("subscription rejection and cleanup: failed subscriptions can be retried", () => {
  subscriptionManager.add(subscription("test-topic", vi.fn()))
  expect(subscriptionManager.getAllSubscriptions().map(s => s.name)).toContain("test-topic")

  subscriptionManager.handleMessage({
    type: ChannelMessageType.SUBSCRIPTION_REJECTED,
    topic_stream: "test-topic",
    topic_params: {},
    error: "Access denied",
  })

  expect(subscriptionManager.isConfirmed("test-topic")).toBe(false)
  expect(subscriptionManager.getAllSubscriptions().map(s => s.name)).not.toContain("test-topic")

  // Can subscribe again (treated as a new topic).
  expect(subscriptionManager.add(subscription("test-topic", vi.fn()))).toBe(true)
})

test("resubscribeAll resets confirmations and rebuilds the correct wire form per topic", () => {
  // Stream-only topic with two callbacks (uses first subscription's extra params), plus an
  // unsigned topic with params — each must resubscribe in its own wire form.
  subscriptionManager.add(subscription("topic1", vi.fn(), { room: "room1" }))
  subscriptionManager.add(subscription("topic1", vi.fn(), { room: "room2" }))
  subscriptionManager.add({
    name: "mailbox_view:view_id:abc",
    stream: "mailbox_view",
    topicParams: { view_id: "abc" },
    params: { cached_at: "2026-01-01" },
    callback: vi.fn(),
  })

  subscriptionManager.handleMessage({
    type: ChannelMessageType.SUBSCRIPTION_CONFIRMED,
    topic_stream: "topic1",
    topic_params: {},
  })
  expect(subscriptionManager.isConfirmed("topic1")).toBe(true)

  const messages = subscriptionManager.resubscribeAll()

  expect(subscriptionManager.isConfirmed("topic1")).toBe(false)
  expect(messages).toHaveLength(2)
  expect(messages).toEqual(
    expect.arrayContaining([
      {
        type: ChannelMessageType.SUBSCRIBE,
        topic_stream: "topic1",
        topic_params: {},
        params: { room: "room1" }, // first subscription's params win
      },
      {
        type: ChannelMessageType.SUBSCRIBE,
        topic_stream: "mailbox_view",
        topic_params: { view_id: "abc" },
        params: { cached_at: "2026-01-01" },
      },
    ])
  )
})
