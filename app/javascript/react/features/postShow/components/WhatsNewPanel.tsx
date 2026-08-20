import { UserAvatar } from "~/react/composites/UserAvatar"
import { DateTime } from "~/react/ui/DateTime"

import type { WhatsNew, WhatsNewComment } from "../whatsNew"

interface WhatsNewPanelProps {
  whatsNew: WhatsNew
  onJump: (commentId: string) => void
  onDismiss: () => void
}

function Row({ comment, onJump }: { comment: WhatsNewComment; onJump: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onJump(comment.id)}
      className="w-full flex items-center gap-2 py-1 px-1 -mx-1 rounded hover:bg-base-200 transition group/item text-left"
    >
      <UserAvatar user={comment.user} size="small" />
      <span className="text-xs font-medium text-base-content">{comment.user.display_name}</span>
      <span className="text-xs text-base-content/60 truncate flex-1">{comment.preview}</span>
      <span className="material-symbols-outlined text-sm text-base-content/40 group-hover/item:text-base-content transition">
        arrow_forward
      </span>
    </button>
  )
}

// Dismissable "what's new since last visit" summary. Dismiss is React state
// (server-side last-visit is the source of truth, so a reload re-surfaces it).
// Each row scrolls to and highlights its comment via onJump.
export function WhatsNewPanel({ whatsNew, onJump, onDismiss }: WhatsNewPanelProps) {
  const firstNewCommentId = whatsNew.firstNewCommentId
  return (
    <div className="border border-base-300 rounded-xl shadow-sm mb-6 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-base-300 bg-base-50">
        <span className="text-xs font-semibold text-primary">
          {whatsNew.totalCount} new since <DateTime datetime={whatsNew.lastVisitAt} format="relative" />
        </span>
        <button type="button" onClick={onDismiss} className="btn btn-ghost btn-sm" title="Dismiss">
          Dismiss
        </button>
      </div>

      <div className="divide-y divide-base-300 bg-base-50">
        {whatsNew.decisions.map(({ comment, decidedByName }) => (
          <div key={comment.id} className="px-3 py-2">
            <div className="flex items-center gap-1 text-xs text-base-500 mb-1">
              <span className="material-symbols-outlined text-sm">check_circle</span>
              <span>Decision</span>
            </div>
            <button
              type="button"
              onClick={() => onJump(comment.id)}
              className="w-full flex items-center gap-2 py-1 px-1 -mx-1 rounded hover:bg-base-200 transition group/item text-left"
            >
              <UserAvatar user={comment.user} size="small" />
              <span className="text-xs font-medium text-base-content">{comment.user.display_name}</span>
              {decidedByName && (
                <span className="text-xs text-base-content/40 shrink-0">marked by {decidedByName}</span>
              )}
              <span className="material-symbols-outlined text-sm text-base-content/40 group-hover/item:text-base-content transition ml-auto">
                arrow_forward
              </span>
            </button>
          </div>
        ))}

        {whatsNew.groups.map(group => (
          <div key={group.parentCommentId ?? "top-level"} className="px-3 py-2">
            <div className="flex items-center gap-1 text-xs text-base-500 mb-1">
              {group.parentCommentId ? (
                <>
                  <span className="material-symbols-outlined text-sm">reply</span>
                  <span>
                    Replying to <span className="font-semibold text-base-content">{group.contextAuthorName}</span>
                  </span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-sm">chat_bubble</span>
                  <span>New comment{group.comments.length > 1 ? "s" : ""}</span>
                </>
              )}
            </div>
            <div className="space-y-0.5">
              {group.comments.map(comment => (
                <Row key={comment.id} comment={comment} onJump={onJump} />
              ))}
            </div>
          </div>
        ))}
      </div>

      {firstNewCommentId && (
        <button
          type="button"
          onClick={() => onJump(firstNewCommentId)}
          className="w-full flex items-center justify-center gap-1 px-3 py-2 bg-base-50 text-primary font-medium text-sm hover:bg-primary/10 transition border-t border-base-300"
        >
          <span className="material-symbols-outlined text-sm">arrow_downward</span>
          Jump to first new
        </button>
      )}
    </div>
  )
}
