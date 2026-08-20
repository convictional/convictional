import type { ReactNode } from "react"

interface StickyHeaderProps {
  children: ReactNode
}

export function StickyHeader({ children }: StickyHeaderProps) {
  return (
    <div className="sticky-header">
      <div className="sticky-header-spacer" />
      <div className="sticky-header-card">{children}</div>
    </div>
  )
}
