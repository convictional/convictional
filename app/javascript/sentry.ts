import * as Sentry from "@sentry/browser"

interface SentryUser {
  id: string
  email: string
}

interface InitSentryOptions {
  // The classic HTMX shell stamps a canary counting <head> module scripts onto
  // each transaction: the head holds a fixed set of app-owned module scripts, so
  // a rising count means htmx head-support has started re-executing entry
  // scripts again. The SPA shell has no head-support and omits it.
  headModuleScriptCanary?: boolean
  user?: SentryUser | null
}

// performance.memory is Chrome-only and absent elsewhere.
interface PerformanceWithMemory extends Performance {
  memory?: { usedJSHeapSize: number }
}

// The DSN and release are injected by the server (see layouts/_head and spa
// templates) so the same bundle points at whichever Sentry project the running
// environment is configured for. Without a DSN, init is skipped entirely and
// every Sentry call becomes a safe no-op.
export function initSentry({ headModuleScriptCanary = false, user = null }: InitSentryOptions = {}): void {
  const dsn = window.SENTRY_DSN
  if (!dsn || Sentry.isInitialized()) {
    return
  }

  Sentry.init({
    dsn,
    release: window.SENTRY_RELEASE || undefined,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: 0.2,
    // Stamp client heap size onto each auto-emitted navigation transaction so
    // heap growth over a session is observable in Sentry.
    beforeSendTransaction(event) {
      const perf = performance as PerformanceWithMemory
      if (perf.memory) {
        event.measurements = event.measurements ?? {}
        event.measurements.memory_used_js_heap = { value: perf.memory.usedJSHeapSize, unit: "byte" }
      }
      if (headModuleScriptCanary) {
        event.measurements = event.measurements ?? {}
        event.measurements.head_module_scripts = {
          value: document.head.querySelectorAll('script[type="module"]').length,
          unit: "none",
        }
      }
      return event
    },
  })

  if (user) {
    Sentry.setUser(user)
  }
}
