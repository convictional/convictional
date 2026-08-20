import { useState, type HTMLAttributes } from "react"

import { DecisionMarker } from "~/react/composites/DecisionMarker"
import { ReactionBar } from "~/react/composites/reactions/ReactionBar"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useScrollIntoViewOnEdit } from "~/react/shared/hooks/useScrollIntoViewOnEdit"
import type { Decision, PostComment } from "~/react/shared/types"
import { ReplyComposer } from "./ReplyComposer"

interface CommentActionsProps {
  comment: PostComment
  workspaceId: string
  currentUserId: string
  // The decision anchored to this comment, if any. Drives the inline marker;
  // any workspace member may toggle it (no role gate — R5).
  decision: Decision | undefined
  onReply: (content: string, attachmentClaimId: string, unfurlLinks: boolean) => Promise<unknown>
  onToggleReaction: (reactionType: string) => void
  onToggleDecision: () => void
  // Long-press handlers forwarded to the reaction chips so pressing one opens
  // the mobile action sheet (see Comment).
  chipHandlers?: HTMLAttributes<HTMLButtonElement>
}

// The action row beneath a top-level comment: Reply (expands an inline
// composer), the reaction-grade decision marker, and the reactions affordance.
export function CommentActions({
  comment,
  workspaceId,
  currentUserId,
  decision,
  onReply,
  onToggleReaction,
  onToggleDecision,
  chipHandlers,
}: CommentActionsProps) {
  const [isReplying, setIsReplying] = useState(false)
  // On mobile the undecided "Decide" affordance and the add-reaction menu move
  // into the long-press action sheet (mirroring chat). Reply stays visible.
  const isMobile = useIsMobile()

  // Autofocusing the composer pops the mobile keyboard but doesn't scroll the
  // composer above it. Only mobile needs this (desktop shows it right under the
  // button); the delay lets the keyboard finish opening, and block: "center"
  // clears it where "nearest" would leave the composer pinned behind it.
  const composerRef = useScrollIntoViewOnEdit<HTMLDivElement>(isReplying && isMobile, {
    block: "center",
    delayMs: 300,
  })

  async function handleReply(content: string, attachmentClaimId: string, unfurlLinks: boolean) {
    const result = await onReply(content, attachmentClaimId, unfurlLinks)
    if (result) setIsReplying(false)
    return result
  }

  return (
    <div className="ml-7">
      <div className="flex items-center gap-1 flex-wrap">
        {!isReplying && (
          <button
            type="button"
            // On mobile, match the reaction chips' pill shape and taller tap
            // target so the Reply button sits flush alongside them.
            className={`btn btn-sm ${isMobile ? "rounded-full @mobile:min-h-8" : ""}`}
            onClick={() => setIsReplying(true)}
          >
            <span className="material-symbols-outlined text-base">chat_bubble</span>
            Reply
          </button>
        )}
        {(!isMobile || decision) && <DecisionMarker decision={decision} onToggle={onToggleDecision} />}
        <ReactionBar
          reactions={comment.reactions}
          currentUserId={currentUserId}
          onToggle={onToggleReaction}
          chipHandlers={chipHandlers}
          showMenu={!isMobile}
        />
      </div>
      {isReplying && (
        <div ref={composerRef} className="mt-2">
          <ReplyComposer workspaceId={workspaceId} onSubmit={handleReply} autoFocus />
        </div>
      )}
    </div>
  )
}
