import { useEffect, useRef } from "react"

export interface UseDebouncedSearchOptions {
  debounceMs?: number
  loadingDelayMs?: number
  timeoutMs?: number
  onLoading?: (loading: boolean) => void
  onTimeout?: (showError: boolean) => void
}

// Debounce (300ms) + progressive loading (500ms delay) + timeout (8s).
// Aborts the in-flight request when `query` changes — fetchers must accept the
// returned AbortSignal.
export function useDebouncedSearch(
  query: string,
  enabled: boolean,
  run: (query: string, signal: AbortSignal) => Promise<void>,
  options: UseDebouncedSearchOptions = {}
): void {
  const { debounceMs = 300, loadingDelayMs = 500, timeoutMs = 8000, onLoading, onTimeout } = options
  const runRef = useRef(run)
  const onLoadingRef = useRef(onLoading)
  const onTimeoutRef = useRef(onTimeout)

  useEffect(() => {
    runRef.current = run
    onLoadingRef.current = onLoading
    onTimeoutRef.current = onTimeout
  })

  useEffect(() => {
    if (!enabled) return

    const controller = new AbortController()
    let loadingTimer: number | null = null
    let timeoutTimer: number | null = null

    const clearProgress = () => {
      if (loadingTimer) {
        window.clearTimeout(loadingTimer)
        loadingTimer = null
      }
      if (timeoutTimer) {
        window.clearTimeout(timeoutTimer)
        timeoutTimer = null
      }
      onLoadingRef.current?.(false)
      onTimeoutRef.current?.(false)
    }

    const debounce = window.setTimeout(() => {
      loadingTimer = window.setTimeout(() => onLoadingRef.current?.(true), loadingDelayMs - debounceMs)
      timeoutTimer = window.setTimeout(() => onTimeoutRef.current?.(true), timeoutMs)
      runRef.current(query, controller.signal).then(
        () => {
          if (!controller.signal.aborted) clearProgress()
        },
        () => {
          // Aborted or network error — leave the timeout banner to surface failures.
        }
      )
    }, debounceMs)

    return () => {
      window.clearTimeout(debounce)
      if (loadingTimer) window.clearTimeout(loadingTimer)
      if (timeoutTimer) window.clearTimeout(timeoutTimer)
      controller.abort()
      onLoadingRef.current?.(false)
      onTimeoutRef.current?.(false)
    }
  }, [query, enabled, debounceMs, loadingDelayMs, timeoutMs])
}
