import { type RefObject, useEffect, useLayoutEffect, useRef, useState } from "react"

// After the rendered row set changes under a stationary cursor, the browser
// re-fires neither mouseenter nor CSS :hover, so the row that slides under the
// pointer shows no hover affordances (#8878 — archiving a message left the next
// message with no visible buttons). Track the pointer and, whenever the row ids
// change, hit-test the last pointer position to force the row now under the
// cursor to reveal its actions — until the pointer next moves, when native
// :hover/mouseenter take over again. We hit-test bounding rects rather than
// document.elementFromPoint so the behavior is reachable under jsdom in tests.
export function useHoverRecovery(containerRef: RefObject<HTMLElement | null>, rowIds: string[]): string | null {
  const pointerRef = useRef<{ x: number; y: number } | null>(null)
  const [forcedId, setForcedId] = useState<string | null>(null)

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      pointerRef.current = { x: event.clientX, y: event.clientY }
      // Real movement re-arms native :hover/mouseenter, so hand control back.
      setForcedId(prev => (prev === null ? prev : null))
    }
    document.addEventListener("pointermove", onMove, { passive: true })
    return () => document.removeEventListener("pointermove", onMove)
  }, [])

  const rowKey = rowIds.join(",")
  useLayoutEffect(() => {
    const pointer = pointerRef.current
    const container = containerRef.current
    if (!pointer || !container) return
    const row = Array.from(container.querySelectorAll<HTMLElement>("[data-thread-id]")).find(element => {
      const rect = element.getBoundingClientRect()
      return pointer.x >= rect.left && pointer.x <= rect.right && pointer.y >= rect.top && pointer.y <= rect.bottom
    })
    setForcedId(row?.dataset.threadId ?? null)
  }, [rowKey, containerRef])

  return forcedId
}
