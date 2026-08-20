import { ChannelMessageType, WebSocketMessage } from "~/types/channels"
import { logConnectionFailureToSentry } from "../logging"
import { topicKeyFromMessage } from "../topic"
import { ChannelsBackend } from "./base"
import { WebSocketBackend } from "./websocket"

// Constants
const CHANNEL_NAME = "convictional-channels-shared-connection"
const LOCK_NAME = "convictional-channels-websocket-leader"
const BACKGROUND_GRACE_PERIOD_MS = 10000

// BroadcastChannel message types
enum BroadcastMessageType {
  CONNECTION_STATE = "connection_state",
  WS_MESSAGE = "ws_message",
  SEND_REQUEST = "send_request",
  STATE_REQUEST = "state_request",
}

interface BaseBroadcastMessage {
  type: BroadcastMessageType
}

interface ConnectionStateMessage extends BaseBroadcastMessage {
  type: BroadcastMessageType.CONNECTION_STATE
  isConnected: boolean
}

interface WsMessageBroadcast extends BaseBroadcastMessage {
  type: BroadcastMessageType.WS_MESSAGE
  payload: WebSocketMessage
}

interface SendRequestMessage extends BaseBroadcastMessage {
  type: BroadcastMessageType.SEND_REQUEST
  payload: WebSocketMessage
}

interface StateRequestMessage extends BaseBroadcastMessage {
  type: BroadcastMessageType.STATE_REQUEST
}

type BroadcastMessage = ConnectionStateMessage | WsMessageBroadcast | SendRequestMessage | StateRequestMessage

/**
 * Shares a single WebSocket connection among multiple browser tabs using
 * Web Locks API for leader election and BroadcastChannel for message relay.
 *
 * One tab becomes the "leader" and maintains the actual WebSocket connection.
 * Other tabs ("followers") send/receive messages through the leader via BroadcastChannel.
 */
export class SharedConnectionBackend extends ChannelsBackend {
  private isLeader = false
  private isConnected = false
  private fallbackMode = false

  private broadcastChannel: BroadcastChannel | null = null
  private wsBackend: WebSocketBackend | null = null
  private lockAbortController: AbortController | null = null

  // Leader only: subscription ref counts (for UNSUBSCRIBE)
  private subscriptionCounts = new Map<string, number>()

  // Visibility-gated leadership
  private backgroundReleaseTimeout: ReturnType<typeof setTimeout> | null = null
  private boundVisibilityHandler: (() => void) | null = null

  constructor() {
    super()
    this.fallbackMode = !this.isWebLocksSupported() || !this.isBroadcastChannelSupported()
  }

  async connect(): Promise<void> {
    if (this.fallbackMode) {
      return this.connectFallback()
    }

    this.setupBroadcastChannel()
    this.setupVisibilityHandler()
    this.acquireLeaderLock()
    this.requestStateFromLeader()

    // Return immediately - followers don't wait for WebSocket connection
    // They'll receive CONNECTION_STATE when leader connects
    return Promise.resolve()
  }

  send(message: WebSocketMessage): boolean {
    if (this.fallbackMode) {
      return this.wsBackend?.send(message) ?? false
    }

    if (!this.isConnected) {
      return false
    }

    if (this.isLeader) {
      return this.leaderSend(message)
    }

    // Follower: send via broadcast channel
    return this.sendViaLeader(message)
  }

  getConnectionState(): boolean {
    if (this.fallbackMode || this.isLeader) {
      // Check actual WebSocket state (cached flag may be stale after OS suspend)
      return this.wsBackend?.getConnectionState() ?? false
    }
    return this.isConnected
  }

  disconnect(): void {
    this.cleanup()
  }

  // --- Private: Initialization ---

  private isWebLocksSupported(): boolean {
    return typeof navigator !== "undefined" && "locks" in navigator
  }

  private isBroadcastChannelSupported(): boolean {
    return typeof BroadcastChannel !== "undefined"
  }

  private async connectFallback(): Promise<void> {
    this.wsBackend = new WebSocketBackend()
    this.setupWsBackendListeners()
    return this.wsBackend.connect()
  }

  private setupBroadcastChannel(): void {
    this.broadcastChannel = new BroadcastChannel(CHANNEL_NAME)
    this.broadcastChannel.onmessage = (event: MessageEvent<BroadcastMessage>) => {
      this.handleBroadcastMessage(event.data)
    }
  }

  private setupVisibilityHandler(): void {
    if (typeof document === "undefined") return

    this.boundVisibilityHandler = () => {
      if (document.hidden) {
        this.handleTabHidden()
      } else {
        this.handleTabVisible()
      }
    }
    document.addEventListener("visibilitychange", this.boundVisibilityHandler)
  }

  private handleTabHidden(): void {
    this.cancelBackgroundRelease()

    if (this.isLeader) {
      // Schedule leadership release - don't hold the lock while backgrounded
      this.backgroundReleaseTimeout = setTimeout(() => {
        this.backgroundReleaseTimeout = null
        if (this.isLeader && document.hidden) {
          this.exitLeadershipContention()
        }
      }, BACKGROUND_GRACE_PERIOD_MS)
    } else if (this.lockAbortController) {
      // Stop competing for leadership while hidden
      this.exitLeadershipContention()
    }
  }

  private handleTabVisible(): void {
    this.cancelBackgroundRelease()

    // Re-enter leadership contention if we're not already competing
    if (!this.isLeader && !this.lockAbortController) {
      this.acquireLeaderLock()
      this.requestStateFromLeader()
    }
  }

  private cancelBackgroundRelease(): void {
    if (this.backgroundReleaseTimeout) {
      clearTimeout(this.backgroundReleaseTimeout)
      this.backgroundReleaseTimeout = null
    }
  }

  private exitLeadershipContention(): void {
    this.cancelBackgroundRelease()

    if (this.wsBackend) {
      this.wsBackend.disconnect()
      this.wsBackend = null
    }
    this.subscriptionCounts.clear()
    this.isLeader = false

    // Release lock without re-acquiring
    this.lockAbortController?.abort()
    this.lockAbortController = null

    // Notify local listeners we're disconnected
    if (this.isConnected) {
      this.isConnected = false
      this.emit("disconnected", [])
    }
  }

  private acquireLeaderLock(): void {
    this.lockAbortController = new AbortController()
    const { signal } = this.lockAbortController

    navigator.locks
      .request(LOCK_NAME, { signal }, async () => {
        await this.becomeLeader()

        // Hold the lock until abort() is called
        await new Promise<void>(resolve => {
          if (signal.aborted) {
            resolve()
          } else {
            signal.addEventListener("abort", () => resolve(), { once: true })
          }
        })
      })
      .catch(error => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return
        }
        console.warn("Web Lock acquisition failed, falling back to direct WebSocket:", error)
        this.fallbackMode = true
        this.connectFallback()
      })
  }

  // --- Private: Leader Logic ---

  private async becomeLeader(): Promise<void> {
    this.isLeader = true
    this.isConnected = false
    this.subscriptionCounts.clear()

    // Tell followers to stop sending until we're ready
    this.broadcastConnectionState(false)

    this.wsBackend = new WebSocketBackend()
    this.setupWsBackendListeners()

    try {
      await this.wsBackend.connect()
    } catch {
      // WebSocket connection failed, but we're still leader
      // WebSocketBackend will handle reconnection
    }
  }

  private setupWsBackendListeners(): void {
    if (!this.wsBackend) return

    this.wsBackend.on("connected", () => {
      this.isConnected = true
      this.emit("connected", [])

      if (this.isLeader) {
        this.broadcastConnectionState(true)
      }
    })

    this.wsBackend.on("disconnected", () => {
      this.isConnected = false
      this.emit("disconnected", [])

      if (this.isLeader) {
        this.broadcastConnectionState(false)
      }
    })

    this.wsBackend.on("reconnectExhausted", () => {
      // Log with fallback mode context
      logConnectionFailureToSentry("WebSocket reconnection exhausted", {
        attemptCount: 5, // WebSocketBackend.maxReconnectAttempts
        fallbackMode: this.fallbackMode,
      })

      if (this.isLeader) {
        this.releaseLeadership()
      }
    })

    this.wsBackend.on("message", (message: WebSocketMessage) => {
      // Clear subscription count if server rejected
      if (message.type === ChannelMessageType.SUBSCRIPTION_REJECTED) {
        const key = topicKeyFromMessage(message)
        if (key) this.subscriptionCounts.delete(key)
      }

      this.emit("message", [message])

      if (this.isLeader) {
        this.broadcastWsMessage(message)
      }
    })
  }

  /**
   * Leader's send logic with subscription tracking.
   */
  private leaderSend(message: WebSocketMessage): boolean {
    if (!this.wsBackend) return false

    // Refcount by canonical topic name so both subscribe forms share one server subscription.
    const key =
      message.type === ChannelMessageType.SUBSCRIBE || message.type === ChannelMessageType.UNSUBSCRIBE
        ? topicKeyFromMessage(message)
        : null

    // Handle SUBSCRIBE: increment count, forward to server
    if (message.type === ChannelMessageType.SUBSCRIBE && key) {
      const count = this.subscriptionCounts.get(key) ?? 0
      this.subscriptionCounts.set(key, count + 1)
      return this.wsBackend.send(message)
    }

    // Handle UNSUBSCRIBE: decrement count, only forward when count reaches 0
    if (message.type === ChannelMessageType.UNSUBSCRIBE && key) {
      const count = this.subscriptionCounts.get(key) ?? 0
      if (count <= 1) {
        this.subscriptionCounts.delete(key)
        return this.wsBackend.send(message)
      }
      this.subscriptionCounts.set(key, count - 1)
      return true
    }

    // All other messages: forward directly
    return this.wsBackend.send(message)
  }

  // --- Private: Follower Logic ---

  private sendViaLeader(message: WebSocketMessage): boolean {
    if (!this.broadcastChannel || !this.isConnected) return false

    this.broadcast({
      type: BroadcastMessageType.SEND_REQUEST,
      payload: message,
    })

    return true
  }

  private handleConnectionStateUpdate(newIsConnected: boolean): void {
    const wasConnected = this.isConnected
    this.isConnected = newIsConnected

    if (newIsConnected && !wasConnected) {
      this.emit("connected", [])
    } else if (!newIsConnected && wasConnected) {
      this.emit("disconnected", [])
    }
  }

  // --- Private: BroadcastChannel Message Handling ---

  private handleBroadcastMessage(message: BroadcastMessage): void {
    switch (message.type) {
      case BroadcastMessageType.CONNECTION_STATE:
        if (!this.isLeader) {
          this.handleConnectionStateUpdate(message.isConnected)
        }
        break

      case BroadcastMessageType.WS_MESSAGE:
        if (!this.isLeader) {
          this.emit("message", [message.payload])
        }
        break

      case BroadcastMessageType.SEND_REQUEST:
        if (this.isLeader) {
          this.leaderSend(message.payload)
        }
        break

      case BroadcastMessageType.STATE_REQUEST:
        if (this.isLeader) {
          // Check actual WebSocket state (cached isConnected may be stale after OS suspend)
          const actualState = this.wsBackend?.getConnectionState() ?? false
          if (this.isConnected !== actualState) {
            this.isConnected = actualState
            this.emit(actualState ? "connected" : "disconnected", [])
          }
          this.broadcastConnectionState(actualState)
        }
        break
    }
  }

  // --- Private: Broadcasting ---

  private broadcast(message: BroadcastMessage): void {
    this.broadcastChannel?.postMessage(message)
  }

  private broadcastConnectionState(isConnected: boolean): void {
    this.broadcast({
      type: BroadcastMessageType.CONNECTION_STATE,
      isConnected,
    })
  }

  private broadcastWsMessage(payload: WebSocketMessage): void {
    this.broadcast({
      type: BroadcastMessageType.WS_MESSAGE,
      payload,
    })
  }

  private requestStateFromLeader(): void {
    this.broadcast({
      type: BroadcastMessageType.STATE_REQUEST,
    })
  }

  // --- Private: Leadership ---

  private releaseLeadership(): void {
    this.exitLeadershipContention()

    // Only re-enter contention if tab is visible
    if (typeof document === "undefined" || !document.hidden) {
      this.acquireLeaderLock()
    }
  }

  // --- Private: Cleanup ---

  private cleanup(): void {
    this.cancelBackgroundRelease()

    if (this.boundVisibilityHandler && typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", this.boundVisibilityHandler)
      this.boundVisibilityHandler = null
    }

    if (this.wsBackend) {
      this.wsBackend.disconnect()
      this.wsBackend = null
    }

    // Abort releases held lock (via signal listener) or cancels pending request
    this.lockAbortController?.abort()
    this.lockAbortController = null

    this.broadcastChannel?.close()
    this.broadcastChannel = null

    this.subscriptionCounts.clear()
    this.isLeader = false
    this.isConnected = false
  }
}
