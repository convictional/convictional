declare global {
  interface Window {
    htmx: object & {
      trigger(element: Element, event: string): void
      process(element: Element): void
      defineExtension(name: string, extension: object): void
      swap(
        element: Element,
        html: string,
        options?: { swapStyle?: string },
        swapOptions?: { contextElement?: Element }
      ): void
      remove(element: Element): void
      ajax(method: string, path: string, target: string): Promise<void>
      ajax(method: string, path: string, context: object): Promise<void>
    }
    Alpine: object
    EMAIL_CSS_URL: string
    // Injected by the server (layouts/_head and spa templates) so the bundled
    // @sentry/browser SDK, initialized in main.ts / spa.tsx, targets whichever
    // Sentry project this environment is configured for. Absent when unset.
    SENTRY_DSN?: string
    SENTRY_RELEASE?: string
    SENTRY_USER?: { id: string; email: string }
  }

  interface BeforeInstallPromptEvent extends Event {
    prompt: () => Promise<void>
    userChoice: Promise<{
      outcome: "accepted" | "dismissed"
      platform: string
    }>
  }
}

export {}
