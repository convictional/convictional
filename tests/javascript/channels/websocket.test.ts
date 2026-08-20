import { expect, test, beforeEach, vi, afterEach } from "vitest"
import { WebSocketBackend, WS_POLICY_VIOLATION } from "../../../app/javascript/channels/backends/websocket"
import WS from "vitest-websocket-mock"

let backend: WebSocketBackend
let server: WS

// The backend's reconnect backoff (1s, 2s, …) and 10s stability gate are
// production timings. These tests exercise the same escalation logic, so shrink
// both to a few ms: the ratios the assertions depend on are preserved, but the
// suite no longer sleeps through real backoff windows. mock-socket caches the
// real setTimeout at import time, so fake timers can't drive its handshake —
// scaling the real delays is what keeps these tests both fast and honest.
const RECONNECT_INTERVAL = 30
const STABLE_CONNECTION_DELAY = 500

function useFastReconnectTiming(b: WebSocketBackend): void {
  const timing = b as unknown as { reconnectInterval: number; stableConnectionDelay: number }
  timing.reconnectInterval = RECONNECT_INTERVAL
  timing.stableConnectionDelay = STABLE_CONNECTION_DELAY
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
// Let queued close/open events settle without waiting on any backoff.
const settle = () => sleep(15)
// A window after attempt-1 backoff (RECONNECT_INTERVAL) but before attempt-2
// (2 ×): attempt-1 has fired, attempt-2 has not.
const betweenBackoffs = () => sleep(RECONNECT_INTERVAL * 1.5)
// Long enough that any scheduled reconnect or retry-exhaustion would have fired;
// used to prove that none was scheduled at all.
const quiet = () => sleep(RECONNECT_INTERVAL * 5)

beforeEach(async () => {
  server = new WS("ws://localhost:3000/channels", { jsonProtocol: true })
  backend = new WebSocketBackend()
  useFastReconnectTiming(backend)
})

afterEach(() => {
  backend.disconnect()
  WS.clean()
  setNavigatorOnline(true)
})

function setNavigatorOnline(online: boolean): void {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    get: () => online,
  })
}

test("backend reconnects when connection is lost abnormally", async () => {
  // Initial connection
  await backend.connect()
  await server.connected

  expect(backend.getConnectionState()).toBe(true)

  // Set up event listeners to track reconnection
  const disconnectedCallback = vi.fn()
  const reconnectedCallback = vi.fn()

  backend.on("disconnected", disconnectedCallback)
  backend.on("connected", reconnectedCallback)

  // Simulate abnormal connection loss (1006 = Abnormal Closure)
  server.close({ code: 1006 })

  // Wait for disconnection to be processed
  await settle()

  expect(disconnectedCallback).toHaveBeenCalled()
  expect(backend.getConnectionState()).toBe(false)

  // Create new server for reconnection
  const newServer = new WS("ws://localhost:3000/channels", { jsonProtocol: true })

  // Should reconnect to the new server once the attempt-1 backoff elapses
  await newServer.connected

  expect(reconnectedCallback).toHaveBeenCalled()
  expect(backend.getConnectionState()).toBe(true)

  // Verify reconnected connection works
  const message = { type: "test", data: "reconnected" }
  backend.send(message)

  await expect(newServer).toReceiveMessage(message)
})

test("backend escalates backoff when a connection flaps instead of resetting on open", async () => {
  // Each connection below opens then closes almost immediately — far short of
  // stableConnectionDelay — so backoff must accumulate (attempt-1 then attempt-2)
  // rather than resetting to the floor on every open. This reproduces the
  // deploy-time reconnect storm: instances drain, sockets flap, and a per-open
  // reset would hammer reconnects at the floor indefinitely.
  await backend.connect()
  await server.connected

  // First flap: reconnect scheduled one backoff interval out (attempt 1).
  server.close({ code: 1006 })
  await settle()

  const server2 = new WS("ws://localhost:3000/channels", { jsonProtocol: true })
  await server2.connected

  // Second flap right after opening. With the bug, onopen would have reset
  // backoff and this reconnect would again be attempt-1; with the fix it must
  // escalate to attempt-2 (double the interval).
  server2.close({ code: 1006 })
  await settle()

  const reconnected = vi.fn()
  backend.on("connected", reconnected)
  const server3 = new WS("ws://localhost:3000/channels", { jsonProtocol: true })

  // Past what an attempt-1 backoff would be, but short of attempt-2: had backoff
  // wrongly reset on open, it would already have reconnected here.
  await betweenBackoffs()
  expect(reconnected).not.toHaveBeenCalled()

  // After the full attempt-2 backoff it reconnects.
  await server3.connected
  expect(reconnected).toHaveBeenCalled()
})

test("backend waits for connectivity instead of exhausting retries while offline", async () => {
  await backend.connect()
  await server.connected

  const reconnectExhausted = vi.fn()
  const reconnected = vi.fn()
  backend.on("reconnectExhausted", reconnectExhausted)
  backend.on("connected", reconnected)

  // Client network goes down, then the socket drops abnormally.
  setNavigatorOnline(false)
  server.close({ code: 1006 })
  await settle()

  expect(backend.getConnectionState()).toBe(false)

  // Well past the full retry budget: while offline we must NOT declare the
  // connection permanently exhausted — there's nothing to reach until the
  // network returns. No reconnect should be scheduled either.
  const offlineServer = new WS("ws://localhost:3000/channels", { jsonProtocol: true })
  await quiet()
  expect(reconnectExhausted).not.toHaveBeenCalled()
  expect(reconnected).not.toHaveBeenCalled()

  // Connectivity returns: the browser fires `online` and we reconnect at once.
  setNavigatorOnline(true)
  window.dispatchEvent(new Event("online"))

  await offlineServer.connected
  expect(reconnected).toHaveBeenCalled()
  expect(backend.getConnectionState()).toBe(true)
})

test("backend responds to ping with pong", async () => {
  await backend.connect()
  await server.connected

  // Send a ping message from server
  server.send({ type: "ping" })

  // Should receive pong response
  await expect(server).toReceiveMessage(
    expect.objectContaining({
      type: "pong",
      data: expect.any(String)
    })
  )
})

test("ping messages do not trigger message events", async () => {
  await backend.connect()
  await server.connected

  const messageCallback = vi.fn()
  backend.on("message", messageCallback)

  // Send ping message
  server.send({ type: "ping" })

  // The pong reply proves the ping was received and handled; a ping must not
  // surface as a message event.
  await expect(server).toReceiveMessage(expect.objectContaining({ type: "pong" }))
  expect(messageCallback).not.toHaveBeenCalled()

  // But normal messages should still work
  server.send({ type: "normal_message", topic_stream: "test", data: "test" })

  await vi.waitFor(() =>
    expect(messageCallback).toHaveBeenCalledWith(expect.objectContaining({ type: "normal_message" }))
  )
})

test("backend does not reconnect on policy violation (1008)", async () => {
  await backend.connect()
  await server.connected

  const disconnectedCallback = vi.fn()
  const reconnectedCallback = vi.fn()

  backend.on("disconnected", disconnectedCallback)
  backend.on("connected", reconnectedCallback)

  server.close({ code: WS_POLICY_VIOLATION })

  await settle()
  expect(disconnectedCallback).toHaveBeenCalled()
  expect(backend.getConnectionState()).toBe(false)

  await quiet()
  expect(reconnectedCallback).not.toHaveBeenCalled()
})

test("backend reconnects on normal closure (1000) for deploys", async () => {
  await backend.connect()
  await server.connected

  const disconnectedCallback = vi.fn()
  const reconnectedCallback = vi.fn()

  backend.on("disconnected", disconnectedCallback)
  backend.on("connected", reconnectedCallback)

  server.close({ code: 1000 })

  await settle()
  expect(disconnectedCallback).toHaveBeenCalled()
  expect(backend.getConnectionState()).toBe(false)

  // Create new server to simulate deploy completed
  const newServer = new WS("ws://localhost:3000/channels", { jsonProtocol: true })

  await newServer.connected
  expect(reconnectedCallback).toHaveBeenCalled()
})
