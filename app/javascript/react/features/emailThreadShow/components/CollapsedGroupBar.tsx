interface CollapsedGroupBarProps {
  // Hidden email + comment ("chat") counts. Peeked messages are excluded — the
  // bar summarizes only what expanding it reveals.
  emailCount: number
  chatCount: number
  onExpand: () => void
}

function countLabel(emailCount: number, chatCount: number): string {
  const parts: string[] = []
  if (emailCount > 0) parts.push(`${emailCount} ${emailCount === 1 ? "email" : "emails"}`)
  if (chatCount > 0) parts.push(`${chatCount} ${chatCount === 1 ? "chat" : "chats"}`)
  // The group requires ≥2 hidden entries, but they could in theory all be
  // activity events (uncounted) — fall back to a generic label rather than "".
  return parts.length > 0 ? parts.join(" • ") : "Earlier messages"
}

// The strip between the two peeked messages of a collapsed group. Clicking it
// reveals the hidden run as individual collapsed previews (not full bodies).
// Renders as a full-width row inside the group's single bordered container.
export function CollapsedGroupBar({ emailCount, chatCount, onExpand }: CollapsedGroupBarProps) {
  return (
    <button
      type="button"
      onClick={onExpand}
      data-testid="collapsed-group-bar"
      className="flex w-full items-center gap-2 bg-base-50 px-4 py-2.5 text-left text-xs font-medium text-base-600 transition-colors hover:bg-base-100 cursor-pointer"
    >
      <span className="material-symbols-outlined text-base" aria-hidden="true">
        unfold_more
      </span>
      <span>{countLabel(emailCount, chatCount)}</span>
    </button>
  )
}
