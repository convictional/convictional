import type { RefObject } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { useVisibleOnce } from "~/react/ui/hooks/useVisibleOnce"

interface Options {
  ref: RefObject<HTMLElement | null>
  enabled: boolean
  url: string
  onMarkedRead: () => void
  delayMs?: number
}

// Marks the entry read once the bar has been continuously visible for `delayMs`.
// Returning the POST promise lets useVisibleOnce stay armed on failure and retry
// on the next re-entry — best-effort, and unlike goal visit recording this is
// deliberately retryable rather than once-per-event.
export function useAutoMarkRead({ ref, enabled, url, onMarkedRead, delayMs = 1000 }: Options): void {
  useVisibleOnce(
    {
      ref,
      enabled,
      delayMs,
      onVisible: () =>
        apiFetch(url, { method: "POST" }).then(() => {
          window.dispatchEvent(new CustomEvent("thread-marked-read"))
          onMarkedRead()
        }),
    },
    [url]
  )
}
