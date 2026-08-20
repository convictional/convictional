import { expect, test, beforeEach, vi, afterEach, describe } from "vitest"
import { SharedConnectionBackend } from "../../../app/javascript/channels/backends/sharedConnection"
import WS from "vitest-websocket-mock"

// Mock BroadcastChannel - messages are NOT echoed back to sender (like real BroadcastChannel)
class MockBroadcastChannel {
  static instances: MockBroadcastChannel[] = []
  name: string
  onmessage: ((event: MessageEvent) => void) | null = null

  constructor(name: string) {
    this.name = name
    MockBroadcastChannel.instances.push(this)
  }

  postMessage(message: unknown): void {
    // Broadcast to all OTHER instances with same name (not self)
    for (const instance of MockBroadcastChannel.instances) {
      if (instance !== this && instance.name === this.name && instance.onmessage) {
        instance.onmessage(new MessageEvent("message", { data: message }))
      }
    }
  }

  close(): void {
    const index = MockBroadcastChannel.instances.indexOf(this)
    if (index > -1) {
      MockBroadcastChannel.instances.splice(index, 1)
    }
  }

  static clear(): void {
    MockBroadcastChannel.instances = []
  }
}

// Mock Web Locks API
interface LockRequest {
  resolve: () => void
  callback: () => Promise<void>
}

class MockLockManager {
  private heldLocks = new Map<string, LockRequest>()
  private waitingQueue = new Map<string, LockRequest[]>()

  async request(
    name: string,
    options: { signal?: AbortSignal },
    callback: () => Promise<void>
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      if (options.signal?.aborted) {
        reject(new DOMException("Aborted", "AbortError"))
        return
      }

      const request: LockRequest = { resolve, callback }

      options.signal?.addEventListener("abort", () => {
        // Abort only affects pending requests, not held locks (per Web Locks API spec)
        const queue = this.waitingQueue.get(name)
        if (queue) {
          const index = queue.indexOf(request)
          if (index > -1) {
            queue.splice(index, 1)
            reject(new DOMException("Aborted", "AbortError"))
          }
        }
      })

      if (this.heldLocks.has(name)) {
        // Lock is held, queue this request
        if (!this.waitingQueue.has(name)) {
          this.waitingQueue.set(name, [])
        }
        this.waitingQueue.get(name)!.push(request)
      } else {
        // Lock is free, grant it
        this.grantLock(name, request)
      }
    })
  }

  private async grantLock(name: string, request: LockRequest): Promise<void> {
    this.heldLocks.set(name, request)
    try {
      await request.callback()
    } finally {
      this.releaseLock(name)
    }
    request.resolve()
  }

  private releaseLock(name: string): void {
    this.heldLocks.delete(name)
    // Grant to next in queue
    const queue = this.waitingQueue.get(name)
    if (queue && queue.length > 0) {
      const nextRequest = queue.shift()!
      this.grantLock(name, nextRequest)
    }
  }

  clear(): void {
    this.heldLocks.clear()
    this.waitingQueue.clear()
  }
}

let server: WS
let mockLockManager: MockLockManager

beforeEach(() => {
  server = new WS("ws://localhost:3000/channels", { jsonProtocol: true })
  mockLockManager = new MockLockManager()
  MockBroadcastChannel.clear()

  // Mock globals
  vi.stubGlobal("BroadcastChannel", MockBroadcastChannel)
  vi.stubGlobal("navigator", {
    locks: mockLockManager,
  })
})

afterEach(() => {
  WS.clean()
  mockLockManager.clear()
  MockBroadcastChannel.clear()
  vi.unstubAllGlobals()
})

describe("SharedConnectionBackend", () => {
  describe("fallback mode", () => {
    test("falls back to direct WebSocket when Web Locks unavailable", async () => {
      vi.stubGlobal("navigator", {})

      const backend = new SharedConnectionBackend()
      await backend.connect()
      await server.connected

      expect(backend.getConnectionState()).toBe(true)

      backend.disconnect()
    })

    test("falls back to direct WebSocket when BroadcastChannel unavailable", async () => {
      vi.stubGlobal("BroadcastChannel", undefined)

      const backend = new SharedConnectionBackend()
      await backend.connect()
      await server.connected

      expect(backend.getConnectionState()).toBe(true)

      backend.disconnect()
    })
  })

  describe("leader election", () => {
    test("first tab becomes leader and connects WebSocket", async () => {
      const backend = new SharedConnectionBackend()
      const connectedCallback = vi.fn()
      backend.on("connected", connectedCallback)

      await backend.connect()

      // Before WebSocket connects, send should return false
      expect(backend.getConnectionState()).toBe(false)
      expect(backend.send({ type: "test", topic_stream: "t1" })).toBe(false)

      // Wait for leader to establish WebSocket
      await server.connected

      expect(backend.getConnectionState()).toBe(true)
      expect(connectedCallback).toHaveBeenCalled()
      expect(backend.send({ type: "test", topic_stream: "t1" })).toBe(true)

      backend.disconnect()
    })

    test("leader broadcasts connection state to followers", async () => {
      const leader = new SharedConnectionBackend()
      await leader.connect()
      await server.connected

      // Second backend joins as follower
      const follower = new SharedConnectionBackend()
      const followerConnected = vi.fn()
      follower.on("connected", followerConnected)

      await follower.connect()

      // Wait for broadcast to be received
      await new Promise(resolve => setTimeout(resolve, 20))

      expect(follower.getConnectionState()).toBe(true)
      expect(followerConnected).toHaveBeenCalled()

      leader.disconnect()
      follower.disconnect()
    })
  })

  describe("message relay", () => {
    test("leader relays WebSocket messages to followers", async () => {
      const leader = new SharedConnectionBackend()
      await leader.connect()
      await server.connected

      const follower = new SharedConnectionBackend()
      await follower.connect()
      await new Promise(resolve => setTimeout(resolve, 20))

      const followerMessage = vi.fn()
      follower.on("message", followerMessage)

      // Server sends message
      server.send({ type: "test_message", topic_stream: "topic1", data: "hello" })

      await new Promise(resolve => setTimeout(resolve, 20))

      expect(followerMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: "test_message", data: "hello" })
      )

      leader.disconnect()
      follower.disconnect()
    })

    test("follower sends messages via leader", async () => {
      const leader = new SharedConnectionBackend()
      await leader.connect()
      await server.connected

      const follower = new SharedConnectionBackend()
      await follower.connect()
      await new Promise(resolve => setTimeout(resolve, 20))

      // Follower sends a message
      follower.send({ type: "typing", topic_stream: "topic1", is_typing: true })

      await expect(server).toReceiveMessage(
        expect.objectContaining({
          type: "typing",
          is_typing: true,
        })
      )

      leader.disconnect()
      follower.disconnect()
    })
  })

  describe("subscription management", () => {
    test("only sends UNSUBSCRIBE when last tab unsubscribes", async () => {
      const leader = new SharedConnectionBackend()
      await leader.connect()
      await server.connected

      const follower = new SharedConnectionBackend()
      await follower.connect()
      await new Promise(resolve => setTimeout(resolve, 20))

      // Both subscribe (both forwarded to server)
      leader.send({ type: "subscribe", topic_stream: "topic1", params: {} })
      await server.nextMessage
      follower.send({ type: "subscribe", topic_stream: "topic1", params: {} })
      await server.nextMessage

      // Should have 2 subscribes
      expect(server.messages).toHaveLength(2)

      // Leader unsubscribes - should NOT send UNSUBSCRIBE (follower still subscribed)
      leader.send({ type: "unsubscribe", topic_stream: "topic1" })
      await new Promise(resolve => setTimeout(resolve, 20))

      // Should still only have the 2 subscribes (no unsubscribe yet)
      expect(server.messages).toHaveLength(2)

      // Follower unsubscribes - NOW should send UNSUBSCRIBE
      follower.send({ type: "unsubscribe", topic_stream: "topic1" })

      await expect(server).toReceiveMessage(
        expect.objectContaining({ type: "unsubscribe", topic_stream: "topic1" })
      )

      leader.disconnect()
      follower.disconnect()
    })
  })

  describe("leadership transfer", () => {
    test("hidden leader releases lock on WebSocket disconnect", async () => {
      const leader = new SharedConnectionBackend()
      await leader.connect()
      await server.connected

      const follower = new SharedConnectionBackend()
      const followerConnected = vi.fn()
      follower.on("connected", followerConnected)
      await follower.connect()
      await new Promise(resolve => setTimeout(resolve, 20))

      expect(follower.getConnectionState()).toBe(true)
      followerConnected.mockClear()

      // Simulate leader tab being hidden
      vi.stubGlobal("document", { hidden: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })

      // Close old server and create new one immediately so new leader can connect
      server.close()
      const newServer = new WS("ws://localhost:3000/channels", { jsonProtocol: true })

      // Wait for leadership transfer and new connection
      await new Promise(resolve => setTimeout(resolve, 40))

      // Follower should have become leader and connected
      await newServer.connected
      expect(followerConnected).toHaveBeenCalled()
      expect(follower.getConnectionState()).toBe(true)

      leader.disconnect()
      follower.disconnect()
    })

    test("new leader broadcasts CONNECTION_STATE=false to other followers", async () => {
      // 3 tabs: leader, follower1, follower2
      const leader = new SharedConnectionBackend()
      await leader.connect()
      await server.connected

      const follower1 = new SharedConnectionBackend()
      await follower1.connect()

      const follower2 = new SharedConnectionBackend()
      const disconnectedCallback = vi.fn()
      follower2.on("disconnected", disconnectedCallback)
      await follower2.connect()

      await new Promise(resolve => setTimeout(resolve, 20))

      // Both followers are connected via leader
      expect(follower1.getConnectionState()).toBe(true)
      expect(follower2.getConnectionState()).toBe(true)

      // Leader disconnects - follower1 becomes new leader
      // The bug fix: new leader broadcasts CONNECTION_STATE=false before its WebSocket is ready
      // This prevents other followers from sending messages that would be lost
      leader.disconnect()
      await new Promise(resolve => setTimeout(resolve, 20))

      // follower2 should have received CONNECTION_STATE=false from new leader
      // (it may have also received CONNECTION_STATE=true once new leader's WebSocket connected)
      expect(disconnectedCallback).toHaveBeenCalled()

      follower1.disconnect()
      follower2.disconnect()
    })
  })

  describe("disconnection", () => {
    test("leader broadcasts disconnection state", async () => {
      const leader = new SharedConnectionBackend()
      await leader.connect()
      await server.connected

      const follower = new SharedConnectionBackend()
      await follower.connect()
      await new Promise(resolve => setTimeout(resolve, 20))

      const followerDisconnected = vi.fn()
      follower.on("disconnected", followerDisconnected)

      // Simulate WebSocket disconnection
      server.close()
      await new Promise(resolve => setTimeout(resolve, 20))

      expect(follower.getConnectionState()).toBe(false)
      expect(followerDisconnected).toHaveBeenCalled()

      leader.disconnect()
      follower.disconnect()
    })
  })

  describe("reconnection exhaustion", () => {
    test("leader releases lock when reconnection attempts exhausted", async () => {
      const leader = new SharedConnectionBackend()
      await leader.connect()
      await server.connected

      const follower = new SharedConnectionBackend()
      const followerConnected = vi.fn()
      follower.on("connected", followerConnected)
      await follower.connect()
      await new Promise(resolve => setTimeout(resolve, 20))

      expect(follower.getConnectionState()).toBe(true)
      followerConnected.mockClear()

      // Ensure document is NOT hidden (so leadership won't be released for that reason)
      vi.stubGlobal("document", { hidden: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })

      // Access the internal wsBackend to directly emit reconnectExhausted
      // This simulates what happens after 5 failed reconnection attempts
      const wsBackend = (leader as unknown as { wsBackend: { emit: (event: string, args: unknown[]) => void } }).wsBackend
      wsBackend.emit("reconnectExhausted", [])

      await new Promise(resolve => setTimeout(resolve, 20))

      // Close old server and create new one for follower to connect to as new leader
      server.close()
      await new Promise(resolve => setTimeout(resolve, 20))
      const newServer = new WS("ws://localhost:3000/channels", { jsonProtocol: true })
      await new Promise(resolve => setTimeout(resolve, 20))

      // Follower should have become leader and connected
      await newServer.connected
      expect(followerConnected).toHaveBeenCalled()
      expect(follower.getConnectionState()).toBe(true)

      leader.disconnect()
      follower.disconnect()
      newServer.close()
    })
  })
})
