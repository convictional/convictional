import { useCallback, useEffect, useRef } from "react"

// Fire `onStall` when `stallMs` elapses without a keep-alive while `enabled`. The timer arms
// automatically when `enabled` flips true and clears when it flips false; call the returned
// `reset()` on each keep-alive signal (e.g. a channel event) to push the deadline out. `reset()`
// is stable and imperative — calling it never re-renders — so a stream of keep-alives doesn't
// churn the consumer. It no-ops while disabled, so a stray event on a settled consumer can't arm a
// timer that later fires `onStall`. `onStall` is read through a ref so an unstable callback doesn't
// re-arm on its own. Used to bound a "still working…" state driven by an external signal that may
// never arrive (e.g. a `mailbox_view` generation that dies server-side without broadcasting).
export function useStallWatchdog({
  enabled,
  stallMs,
  onStall,
}: {
  enabled: boolean
  stallMs: number
  onStall: () => void
}): { reset: () => void } {
  const onStallRef = useRef(onStall)
  const enabledRef = useRef(enabled)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Mirror the latest values into refs after commit (never during render) so `reset()` can stay
  // stable while still reading current state. This effect is declared first, so it runs before the
  // arming effect below in the same commit — the initial `reset()` there sees the fresh `enabled`.
  useEffect(() => {
    onStallRef.current = onStall
    enabledRef.current = enabled
  })

  const reset = useCallback(() => {
    if (!enabledRef.current) return
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => onStallRef.current(), stallMs)
  }, [stallMs])

  useEffect(() => {
    if (!enabled) return
    reset()
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [enabled, reset])

  return { reset }
}
