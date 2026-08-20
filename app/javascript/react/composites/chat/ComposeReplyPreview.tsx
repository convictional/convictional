import type { ReplyPreview } from "~/react/shared/types"

interface ComposeReplyPreviewProps {
  replyTo: ReplyPreview
  onClear: () => void
}

export function ComposeReplyPreview({ replyTo, onClear }: ComposeReplyPreviewProps) {
  return (
    <div className="flex items-center gap-2 mb-1 pl-2 border-l-2 border-primary">
      <div className="flex-1 min-w-0 text-xs text-base-content/70 truncate">
        <span className="font-semibold">{replyTo.user_name}</span>
        <span className="ml-1">{replyTo.content_preview}</span>
      </div>
      <button
        type="button"
        onClick={onClear}
        className="btn btn-xs btn-ghost btn-square shrink-0"
        aria-label="Cancel reply"
      >
        <span className="material-symbols-outlined text-sm">close</span>
      </button>
    </div>
  )
}
