import { expect, test, beforeEach, vi, afterEach } from "vitest"
import { ChannelsClient } from "../../../app/javascript/channels/client"
import { ChannelMessageType } from "../../../app/javascript/types/channels"
import WS from "vitest-websocket-mock"

let client: ChannelsClient
let server: WS

beforeEach(async () => {
  server = new WS("ws://localhost:3000/channels", { jsonProtocol: true })
  client = new ChannelsClient()
})

afterEach(() => {
  client.disconnect()
  WS.clean()
})

test("client manages subscriptions and sends messages to server", async () => {
  await client.connect()
  await server.connected

  // Subscribe to a topic
  client.subscribeTo("test-topic", {}, vi.fn())
  await expect(server).toReceiveMessage({
    type: ChannelMessageType.SUBSCRIBE,
    topic_stream: "test-topic",
    topic_params: {},
    params: {},
  })

  // broadcastTo names the topic via (stream, params) and fills in topic_stream/topic_params
  client.broadcastTo("broadcast-test", {}, { type: ChannelMessageType.TYPING, is_typing: true })
  await expect(server).toReceiveMessage({
    type: ChannelMessageType.TYPING,
    topic_stream: "broadcast-test",
    topic_params: {},
    is_typing: true,
  })

  const subscription = client.subscribeTo("unsubscribe-topic", {}, vi.fn())
  await expect(server).toReceiveMessage({
    type: ChannelMessageType.SUBSCRIBE,
    topic_stream: "unsubscribe-topic",
    topic_params: {},
    params: {},
  })

  client.unsubscribe(subscription)
  await expect(server).toReceiveMessage({
    type: ChannelMessageType.UNSUBSCRIBE,
    topic_stream: "unsubscribe-topic",
    topic_params: {},
  })
})

test("client re-subscribes to topics on reconnection", async () => {
  await client.connect()
  await server.connected

  client.subscribeTo("topic1", {}, vi.fn())
  client.subscribeTo("topic2", {}, vi.fn())

  await expect(server).toReceiveMessage({
    type: ChannelMessageType.SUBSCRIBE,
    topic_stream: "topic1",
    topic_params: {},
    params: {},
  })
  await expect(server).toReceiveMessage({
    type: ChannelMessageType.SUBSCRIBE,
    topic_stream: "topic2",
    topic_params: {},
    params: {},
  })

  server.close()
  await new Promise(resolve => setTimeout(resolve, 10))

  const newServer = new WS("ws://localhost:3000/channels", { jsonProtocol: true })

  await client.connect()
  await newServer.connected

  await expect(newServer).toReceiveMessage({
    type: ChannelMessageType.SUBSCRIBE,
    topic_stream: "topic1",
    topic_params: {},
    params: {},
  })
  await expect(newServer).toReceiveMessage({
    type: ChannelMessageType.SUBSCRIBE,
    topic_stream: "topic2",
    topic_params: {},
    params: {},
  })
})

test("client emits reconnected event only on actual reconnections, not first connections", async () => {
  const connectedCallback = vi.fn()
  const reconnectedCallback = vi.fn()

  client.on("connected", connectedCallback)
  client.on("reconnected", reconnectedCallback)

  // First connection should not emit reconnected
  await client.connect()
  await server.connected

  expect(connectedCallback).toHaveBeenCalledTimes(1)
  expect(reconnectedCallback).not.toHaveBeenCalled()

  // Simulate disconnection and reconnection
  server.close()
  await new Promise(resolve => setTimeout(resolve, 10))

  const newServer = new WS("ws://localhost:3000/channels", { jsonProtocol: true })

  await client.connect()
  await newServer.connected

  // Now both connected and reconnected should have been called
  expect(connectedCallback).toHaveBeenCalledTimes(2)
  expect(reconnectedCallback).toHaveBeenCalledTimes(1)
})

test("client emits reconnected event on multiple reconnections", async () => {
  const reconnectedCallback = vi.fn()
  client.on("reconnected", reconnectedCallback)

  // Initial connection
  await client.connect()
  await server.connected

  expect(reconnectedCallback).not.toHaveBeenCalled()

  // First reconnection
  server.close()
  await new Promise(resolve => setTimeout(resolve, 10))

  const server2 = new WS("ws://localhost:3000/channels", { jsonProtocol: true })
  await client.connect()
  await server2.connected

  expect(reconnectedCallback).toHaveBeenCalledTimes(1)

  // Second reconnection
  server2.close()
  await new Promise(resolve => setTimeout(resolve, 10))

  const server3 = new WS("ws://localhost:3000/channels", { jsonProtocol: true })
  await client.connect()
  await server3.connected

  expect(reconnectedCallback).toHaveBeenCalledTimes(2)
})
