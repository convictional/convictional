import { useEffect, useRef } from "react"
import type { DependencyList, RefObject } from "react"

interface Options {
  ref: RefObject<HTMLElement | null>
  onVisible: () => void | Promise<unknown>
  enabled?: boolean
  delayMs?: number
}

/**
 * Fire `onVisible` once when the `ref`'d element has been continuously visible
 * for `delayMs`. A pending timer is cancelled if the element leaves before the
 * delay elapses, so a quick scroll-past never fires.
 *
 * Semantics:
 * - Edge-triggered: fires on a not-visible → visible crossing, never again
 *   while the element stays continuously in view. This is what prevents a
 *   failing async `onVisible` from retrying in a tight loop.
 * - Success-gated re-arm: if `onVisible` returns a promise that rejects, the
 *   hook stays armed and retries the next time the element re-enters view
 *   (best-effort retry). On resolve — or a synchronous return — it is done and
 *   disconnects until `deps` change.
 * - Re-arms whenever any value in `deps` changes (e.g. a new id to record).
 * - `enabled: false` or a null ref is a no-op.
 *
 * All `deps` entries must be primitives or stable refs — an inline object would
 * re-create the observer every render.
 */
export function useVisibleOnce(
  { ref, onVisible, enabled = true, delayMs = 0 }: Options,
  deps: DependencyList = []
): void {
  const onVisibleRef = useRef(onVisible)
  onVisibleRef.current = onVisible

  useEffect(() => {
    if (!enabled) return
    const el = ref.current
    if (!el) return

    let done = false
    let inFlight = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const fire = () => {
      timer = null
      if (done || inFlight) return
      const result = onVisibleRef.current()
      if (result instanceof Promise) {
        inFlight = true
        result.then(
          () => {
            done = true
            inFlight = false
            observer.disconnect()
          },
          () => {
            // Rejected: stay armed so a later re-entry retries.
            inFlight = false
          }
        )
      } else {
        done = true
        observer.disconnect()
      }
    }

    const observer = new IntersectionObserver(entries => {
      const visible = entries.some(e => e.isIntersecting)
      if (visible && !done && !inFlight && timer === null) {
        timer = setTimeout(fire, delayMs)
      } else if (!visible && timer !== null) {
        clearTimeout(timer)
        timer = null
      }
    })

    observer.observe(el)
    return () => {
      observer.disconnect()
      if (timer !== null) clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref, enabled, delayMs, ...deps])
}
