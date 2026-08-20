import type { ReactNode } from "react"

import { EmptyStateSurface } from "./EmptyStateSurface"

interface EmptyStateProps {
  title?: string
  text?: string
  children?: ReactNode
}

// The shared empty state, rendered on EmptyStateSurface. The title uses the brand accent serif
// (loretta) at its natural weight — the same face the app gives headings — so empty states read as
// authored rather than system chrome; the body is a softly muted token, not a blunt opacity.
// The lightweight text block; EmptyStateSurface is the animated container it renders on.
export function EmptyState({ title, text, children }: EmptyStateProps) {
  return (
    <EmptyStateSurface className="flex flex-col items-center justify-center px-6 py-16 text-center">
      {title && <p className="font-accent text-lg text-base-content text-balance">{title}</p>}
      {text && (
        <p className={`mt-1.5 max-w-xs text-sm text-base-content/55 text-pretty ${children ? "mb-4" : ""}`}>{text}</p>
      )}
      {children}
    </EmptyStateSurface>
  )
}
