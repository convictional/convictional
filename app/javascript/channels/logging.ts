import * as Sentry from "@sentry/browser"

/**
 * Logs WebSocket connection failures to Sentry with structured context
 */
export function logConnectionFailureToSentry(
  message: string,
  context: {
    attemptCount?: number
    fallbackMode?: boolean
  }
): void {
  Sentry.withScope(scope => {
    // Add searchable tags for filtering in Sentry UI
    if (context.attemptCount !== undefined) {
      scope.setTag("websocket.attempt_count", context.attemptCount.toString())
    }
    if (context.fallbackMode !== undefined) {
      scope.setTag("websocket.fallback_mode", context.fallbackMode.toString())
    }

    // Add structured context for event details
    scope.setContext("websocket_connection", {
      attemptCount: context.attemptCount,
      fallbackMode: context.fallbackMode,
      timestamp: new Date().toISOString(),
    })

    // Capture clean message without embedded context
    scope.captureMessage(message, "warning")
  })
}
