import * as Sentry from "@sentry/browser"

import { WebSocketMessage, ChannelMessageType } from "~/types/channels"
import { logConnectionFailureToSentry } from "../logging"
import { ChannelsBackend } from "./base"

export const WS_POLICY_VIOLATION = 1008

/**
 * Uses a WebSocket connection to send/receive channels messages.
 */
export class WebSocketBackend extends ChannelsBackend {
  private connection: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectInterval = 1000
  private maxReconnectDelay = 30000
  private reconnectTimer: number | null = null
  // A connection must stay open this long before we trust it and reset backoff.
  // Without this gate, a connection that opens then drops immediately (a "flap",
  // e.g. when instances are draining during a deploy) would reset backoff on
  // every open and reconnect at the 1s floor forever, never escalating the delay.
  private stableConnectionDelay = 10000
  private stableTimer: number | null = null
  private stopped = false
  // Set while we're parked waiting for the browser to report connectivity is
  // back (the `online` event). The retry budget is for server-side hiccups, not
  // for a client whose own network is down — see attemptReconnect.
  private boundOnlineHandler: (() => void) | null = null

  constructor() {
    super()
  }

  async connect(): Promise<void> {
    const state = this.connection?.readyState
    if (state === WebSocket.CONNECTING || state === WebSocket.OPEN) {
      return
    }

    this.cleanupConnection()

    const protocol = self.location.protocol === "https:" ? "wss:" : "ws:"
    const wsUrl = `${protocol}//${self.location.host}/channels`

    this.connection = new WebSocket(wsUrl)

    return new Promise((resolve, reject) => {
      if (!this.connection) {
        reject(new Error("Failed to create WebSocket connection"))
        return
      }

      const connection = this.connection

      connection.onopen = () => {
        if (connection !== this.connection) return

        // Connected — we're no longer waiting on connectivity to return.
        this.clearOnlineHandler()

        Sentry.addBreadcrumb({
          category: "websocket",
          message: "WebSocket connection opened",
          level: "info",
        })

        // Only credit the connection as stable — and reset backoff — once it has
        // held for stableConnectionDelay. Resetting here on open would let a
        // flapping connection retry at the 1s floor indefinitely (see field doc).
        this.clearStableTimer()
        this.stableTimer = window.setTimeout(() => {
          this.reconnectAttempts = 0
        }, this.stableConnectionDelay)

        this.emit("connected", [])
        resolve()
      }

      connection.onmessage = (event: MessageEvent) => {
        if (connection !== this.connection) return

        try {
          const data = JSON.parse(event.data)
          if (data.type === ChannelMessageType.PING) {
            this.send({ type: ChannelMessageType.PONG, data: Date.now().toString() })
            return
          }
          Sentry.addBreadcrumb({
            category: "websocket",
            message: `Received: ${data.type}${data.topic_stream ? ` on ${data.topic_stream}` : ""}`,
            level: "info",
          })
          this.emit("message", [data])
        } catch (error) {
          if (error instanceof SyntaxError) {
            console.warn("WebSocket received invalid JSON message:", event.data)
          } else {
            console.error("Error handling WebSocket message:", error)
            throw error
          }
        }
      }

      connection.onclose = (event: CloseEvent) => {
        if (connection !== this.connection) return

        // Cancel the pending stability credit; this connection didn't last.
        this.clearStableTimer()

        Sentry.addBreadcrumb({
          category: "websocket",
          message: `WebSocket closed (code: ${event.code}${event.wasClean ? "" : ", unclean"})`,
          level: event.wasClean ? "info" : "warning",
        })

        this.emit("disconnected", [])

        if (this.shouldReconnect(event.code)) {
          this.attemptReconnect()
        }
      }

      connection.onerror = (error: Event) => {
        if (connection !== this.connection) return

        Sentry.addBreadcrumb({
          category: "websocket",
          message: "WebSocket error",
          level: "error",
        })

        reject(error)
      }
    })
  }

  send(message: WebSocketMessage): boolean {
    if (!this.getConnectionState() || !this.connection) {
      return false
    }

    Sentry.addBreadcrumb({
      category: "websocket",
      message: `Sent: ${message.type}${"topic_stream" in message && message.topic_stream ? ` on ${message.topic_stream}` : ""}`,
      level: "info",
    })

    this.connection.send(JSON.stringify(message))
    return true
  }

  getConnectionState(): boolean {
    return this.connection?.readyState === WebSocket.OPEN
  }

  disconnect(): void {
    this.stopped = true
    this.clearReconnectTimer()
    this.clearOnlineHandler()
    this.reconnectAttempts = this.maxReconnectAttempts
    this.cleanupConnection()
  }

  private shouldReconnect(closeCode: number): boolean {
    return closeCode !== WS_POLICY_VIOLATION
  }

  private cleanupConnection(): void {
    this.clearStableTimer()
    if (this.connection) {
      this.connection.onopen = null
      this.connection.onmessage = null
      this.connection.onclose = null
      this.connection.onerror = null

      if (this.connection.readyState === WebSocket.OPEN) {
        this.connection.close()
      }

      this.connection = null
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private clearStableTimer(): void {
    if (this.stableTimer) {
      clearTimeout(this.stableTimer)
      this.stableTimer = null
    }
  }

  private clearOnlineHandler(): void {
    if (this.boundOnlineHandler) {
      window.removeEventListener("online", this.boundOnlineHandler)
      this.boundOnlineHandler = null
    }
  }

  // Park until the browser signals connectivity is back, then reconnect from a
  // clean slate. Registered instead of burning the retry budget while offline.
  private waitForOnline(): void {
    if (this.boundOnlineHandler) {
      return
    }

    this.boundOnlineHandler = () => {
      this.clearOnlineHandler()
      if (this.stopped) return

      Sentry.addBreadcrumb({
        category: "websocket",
        message: "Connectivity returned, reconnecting WebSocket",
        level: "info",
      })

      this.clearReconnectTimer()
      this.reconnectAttempts = 0
      this.connect().catch(() => {
        // Still unreachable despite the online event; fall back to normal backoff.
      })
    }

    Sentry.addBreadcrumb({
      category: "websocket",
      message: "Client offline, waiting for connectivity before reconnecting",
      level: "info",
    })

    window.addEventListener("online", this.boundOnlineHandler)
  }

  private attemptReconnect(): void {
    if (this.stopped) {
      return
    }

    // A dead client network (laptop asleep, Wi-Fi handoff, tunnel drop) routinely
    // outlasts the ~31s retry budget. Spending all attempts against a network the
    // browser already knows is down just declares permanent failure prematurely,
    // and there's nothing to reconnect to until connectivity returns. Park on the
    // `online` event instead so we resume the moment the network is back.
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      this.waitForOnline()
      return
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      // Log to Sentry before emitting event
      logConnectionFailureToSentry("WebSocket reconnection exhausted", {
        attemptCount: this.maxReconnectAttempts,
        fallbackMode: false, // WebSocketBackend doesn't track this
      })

      this.emit("reconnectExhausted", [])
      return
    }

    this.reconnectAttempts++
    const delay = Math.min(this.reconnectInterval * Math.pow(2, this.reconnectAttempts - 1), this.maxReconnectDelay)

    this.reconnectTimer = window.setTimeout(() => {
      this.connect().catch(() => {
        console.warn(
          `WebSocket reconnection attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} failed, will retry in ${delay * 2}ms`
        )
      })
    }, delay)
  }
}
