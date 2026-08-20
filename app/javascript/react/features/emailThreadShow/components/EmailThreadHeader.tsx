import type { ReactNode } from "react"

import { StickyHeader } from "~/react/ui/StickyHeader"

interface EmailThreadHeaderProps {
  // The MailboxActionBar — the only thing left in the sticky header now that the
  // title and shared/assigned badging live in the content area below it.
  actionBar: ReactNode
}

export function EmailThreadHeader({ actionBar }: EmailThreadHeaderProps) {
  return (
    <StickyHeader>
      <div className="flex items-center justify-between gap-2 p-2">{actionBar}</div>
    </StickyHeader>
  )
}
