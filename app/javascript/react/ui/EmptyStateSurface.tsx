import { type ReactNode, useEffect, useState } from "react"

interface EmptyStateSurfaceProps {
  className?: string
  children: ReactNode
}

// The shared backdrop for first-run / empty states:
//  - a soft top-down wash from the base-200 token (theme-safe, no accent tint),
//  - a top light-catch on dark only (--empty-state-edge); light needs no line, the wash defines it,
//  - a one-time fade-and-rise on mount, skipped under prefers-reduced-motion.
// The animated container for rich first-run UI; EmptyState is the text block that renders on it.
export function EmptyStateSurface({ className = "", children }: EmptyStateSurfaceProps) {
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(id)
  }, [])

  const start = "color-mix(in srgb, var(--color-base-200) 70%, transparent)"

  return (
    <div
      className={`rounded-[20px] transition duration-300 ease-out motion-reduce:translate-y-0 motion-reduce:opacity-100 motion-reduce:transition-none ${
        shown ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
      } ${className}`}
      style={{
        background: `linear-gradient(180deg, ${start}, transparent)`,
        boxShadow: "inset 0 1px 0 var(--empty-state-edge)",
      }}
    >
      {children}
    </div>
  )
}
