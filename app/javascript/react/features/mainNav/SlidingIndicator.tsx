import { useEffect, useLayoutEffect, useState, type RefObject } from "react"

interface Props {
  containerRef: RefObject<HTMLElement | null>
  // CSS selector inside the container resolving to the element the bar should
  // sit beneath. Either the active link or, if hovering, the hovered link.
  targetSelector: string
  hovering: boolean
}

// 15% horizontal inset off offsetWidth. The "ready" rAF flag gates the
// transition so the bar doesn't slide in from (0,0) on first paint.
// Doesn't honor prefers-reduced-motion — intentional choice for fluid motion
// when sweeping across nav items.
export function SlidingIndicator({ containerRef, targetSelector, hovering }: Props) {
  const [pos, setPos] = useState({ left: 0, width: 0 })
  const [ready, setReady] = useState(false)

  useLayoutEffect(() => {
    const measure = () => {
      const root = containerRef.current
      if (!root) return
      const target = root.querySelector<HTMLElement>(targetSelector)
      if (!target || target.offsetWidth === 0) {
        setPos(p => (p.width === 0 ? p : { ...p, width: 0 }))
        return
      }
      const inset = target.offsetWidth * 0.15
      const left = target.offsetLeft + inset
      const width = target.offsetWidth - inset * 2
      // Bail when the measured value already matches state. Otherwise the
      // post-paint rAF and the immediate measure both fire setPos with the
      // same numbers, React re-commits, and the second style write cancels
      // the in-flight CSS transition mid-slide — visible as a snap, not a
      // glide, when sweeping across the nav links.
      setPos(p => (p.left === left && p.width === width ? p : { left, width }))
    }
    measure()
    // Re-measure after first paint: font swaps and late-loading CSS can shift
    // link widths between commit and paint. The bailout above keeps this from
    // disrupting steady-state hovers.
    const rafId = requestAnimationFrame(measure)

    // ResizeObserver covers viewport resizes (the container resizes with the
    // window) and any internal reflow that changes link widths, so a separate
    // window resize listener would be redundant.
    const root = containerRef.current
    const observer = root && typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null
    observer?.observe(root!)
    return () => {
      cancelAnimationFrame(rafId)
      observer?.disconnect()
    }
  }, [targetSelector, containerRef])

  useEffect(() => {
    const id = requestAnimationFrame(() => setReady(true))
    return () => cancelAnimationFrame(id)
  }, [])

  return (
    <div
      className={`absolute bottom-0 h-[2.5px] rounded-full pointer-events-none ${
        ready ? "transition-all duration-300" : ""
      } ${hovering ? "bg-primary/40" : "bg-primary"}`}
      style={{
        left: `${pos.left}px`,
        width: `${pos.width}px`,
        opacity: pos.width > 0 ? 1 : 0,
        transitionTimingFunction: "var(--ease-premium)",
      }}
    />
  )
}
