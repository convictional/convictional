import * as Sentry from "@sentry/browser"

interface OutOfOrderDelivery {
  chatId: string | null
  messageId: string
  messageCreatedAt: string
  tailCreatedAt?: string
  gapMs: number
}

/**
 * Reports a detected out-of-order chat message delivery to Sentry. Fires only
 * when an incoming message sorts before the message already at the tail — the
 * exact condition the old append-only code rendered wrong — so it is near-zero
 * noise and quantifies how often/how badly delivery reorders. A single message
 * string keeps Sentry aggregating these rather than flooding.
 */
export function reportOutOfOrderDelivery(context: OutOfOrderDelivery): void {
  Sentry.withScope(scope => {
    scope.setContext("chat_out_of_order_delivery", { ...context, timestamp: new Date().toISOString() })
    scope.captureMessage("chat: out-of-order delivery", "warning")
  })
}
