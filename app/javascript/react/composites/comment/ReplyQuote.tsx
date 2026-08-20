import type { ReplyPreview } from "~/react/shared/types"

interface ReplyQuoteProps {
  replyTo: ReplyPreview
  // Scroll to and flash the quoted target. Required so a clickable quote can
  // never silently no-op.
  onScrollTo: (id: string) => void
  // Show a "Loading message..." state in place of the preview while the target
  // is being scrolled into view. Only meaningful when the target may sit outside
  // the rendered window; a fully-rendered list never needs it.
  loading?: boolean
  // Render a soft-deleted target as a clickable button that still jumps toward
  // where the message was, rather than the default inert tombstone. For callers
  // that keep the deleted row in the rendered list, so there's somewhere to go.
  deletedClickable?: boolean
}

// The in-bubble quote block for a quote-reply: a clickable quote that scrolls to
// its target, or an inert tombstone when the target was soft-deleted (unless
// `deletedClickable` opts back into a clickable jump).
export function ReplyQuote({ replyTo, onScrollTo, loading, deletedClickable }: ReplyQuoteProps) {
  const inner = (
    <div className="min-w-0">
      <div className="font-semibold text-xs text-base-content/70">{replyTo.user_name}</div>
      {loading ? (
        <div className="text-xs text-base-content/50 flex items-center gap-1">
          <span className="loading loading-spinner loading-xs" />
          Loading message...
        </div>
      ) : replyTo.is_deleted ? (
        <div className="text-xs italic text-base-content/50">This message was deleted</div>
      ) : (
        <div className="text-xs text-base-content/60 line-clamp-2 wrap-anywhere">{replyTo.content_preview}</div>
      )}
    </div>
  )

  if (replyTo.is_deleted && !deletedClickable) {
    return <div className="flex mb-1.5 pl-2 border-l-2 border-primary/60">{inner}</div>
  }

  return (
    <button
      type="button"
      className="flex w-full text-left mb-1.5 pl-2 border-l-2 border-primary/60 cursor-pointer hover:opacity-80 transition-opacity"
      onClick={() => onScrollTo(replyTo.id)}
    >
      {inner}
    </button>
  )
}
