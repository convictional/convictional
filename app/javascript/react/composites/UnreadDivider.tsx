import { forwardRef } from "react"

import { pluralize } from "~/shared/strings"

interface UnreadDividerProps {
  count: number
  // Label noun, e.g. "message" or "comment". Pluralized for the label and aria-label.
  noun: string
}

// Inline "N new <noun>s" separator rendered before the first unread item in a
// message or comment list, so those surfaces read identically. The forwarded ref
// anchors the imperative scroll-to-unread.
export const UnreadDivider = forwardRef<HTMLDivElement, UnreadDividerProps>(function UnreadDivider(
  { count, noun },
  ref
) {
  const label = count > 99 ? `99+ new ${pluralize(2, noun)}` : `${count} new ${pluralize(count, noun)}`
  return (
    <div ref={ref} className="flex items-center gap-3 my-3" aria-label={`New ${pluralize(2, noun)} divider`}>
      <div className="flex-1 border-t border-info-content/50" />
      <span className="text-xs font-medium text-info-content whitespace-nowrap">{label}</span>
      <div className="flex-1 border-t border-info-content/50" />
    </div>
  )
})
