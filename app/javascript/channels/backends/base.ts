import { ObservableV2 } from "lib0/observable"
import type { WebSocketMessage } from "~/types/channels"

export interface BackendEvents {
  connected: () => void
  disconnected: () => void
  message: (data: WebSocketMessage) => void
  reconnectExhausted: () => void
}

export abstract class ChannelsBackend extends ObservableV2<BackendEvents> {
  abstract connect(): Promise<void>
  abstract send(message: WebSocketMessage): boolean
  abstract getConnectionState(): boolean
  abstract disconnect(): void
}
