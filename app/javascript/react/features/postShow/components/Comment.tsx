import { useCallback, useLayoutEffect, useRef, useState } from "react"

import { ActionSheet } from "~/react/composites/ActionSheet"
import { CommentEditor } from "~/react/composites/comment/CommentEditor"
import { DecisionMarker } from "~/react/composites/DecisionMarker"
import { Markdown } from "~/react/composites/markdown/Markdown"
import { ReactionBar } from "~/react/composites/reactions/ReactionBar"
import { stripPreviewedAttachmentLink } from "~/react/composites/stripAttachmentLink"
import { UserAvatar } from "~/react/composites/UserAvatar"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useLongPress } from "~/react/shared/hooks/useLongPress"
import type { ReactionType } from "~/react/shared/reactions"
import type { PostComment } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"

import type { CommentThreadProps } from "../commentThread"
import { wasEdited } from "../commentTiming"
import { CommentActions } from "./CommentActions"
import { CommentLinkPreview } from "./CommentLinkPreview"
import { CommentMenu } from "./CommentMenu"
import { RepliesSection } from "./RepliesSection"

interface CommentProps {
  comment: PostComment
  ctx: CommentThreadProps
  isReply?: boolean
}

export function Comment({ comment, ctx, isReply = false }: CommentProps) {
  const [editing, setEditing] = useState(false)
  const [contentExpanded, setContentExpanded] = useState(false)
  const [isClamped, setIsClamped] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)

  const decision = ctx.decisionsByGid.get(comment.global_id)
  const isNew = ctx.newCommentIds.has(comment.id)
  const canModify = comment.user.id === ctx.currentUserId
  const edited = wasEdited(comment.created_at, comment.updated_at)
  const highlighted = ctx.highlightedId === comment.id

  // On mobile the hover overflow menu and reaction tooltip are unreachable, so a
  // long-press on the comment (or a reaction chip) opens the action sheet holding
  // every action (react/decide/copy/edit/delete). The same wiring serves top-level
  // comments and replies. Gated to mobile (UA-based) rather than relying on
  // touch-only events, so a touch-capable desktop keeps its hover affordances
  // instead of also getting the bottom sheet; suppressed while editing so the edit
  // form's text stays selectable.
  const isMobile = useIsMobile()
  const { handlers: longPress, isPressing, highlight } = useLongPress(useCallback(() => setSheetOpen(true), []))
  const pressable = isMobile && !editing

  // Replies are never truncated; top-level comments cap at 4 lines. Show the toggle
  // only when the clamp actually hides something. Measuring rendered overflow (rather
  // than guessing from character count) keeps the button off comments that fit within
  // 4 lines but happen to be long.
  useLayoutEffect(() => {
    const el = contentRef.current
    if (isReply || editing || contentExpanded || !el) return
    // `line-clamp-4` clamps via `display: -webkit-box`, which collapses the box's
    // `scrollHeight` down to the clamped height once its content is a single block
    // child — and the Markdown wrapper is exactly that. So `scrollHeight > clientHeight`
    // never fired and the toggle stayed hidden over truncated content. Read the
    // natural height with the clamp momentarily neutralized (`display: block` disables
    // the `-webkit-box` the clamp needs) and compare against the clamped height. The
    // read-and-restore is synchronous, so the browser never paints the un-clamped state.
    const measure = () => {
      const clampedHeight = el.clientHeight
      el.style.display = "block"
      const naturalHeight = el.scrollHeight
      el.style.display = ""
      setIsClamped(naturalHeight > clampedHeight)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    // ResizeObserver only fires on the box's own (width) changes; web fonts swapping in
    // after first paint and images inside the markdown finishing load both reflow the
    // *content* taller without resizing the pinned box, so re-measure on each. `load` is
    // captured because it does not bubble, and the fonts.ready callback is guarded
    // against firing post-unmount.
    el.addEventListener("load", measure, true)
    let cancelled = false
    void document.fonts?.ready.then(() => {
      if (!cancelled) measure()
    })
    return () => {
      cancelled = true
      observer.disconnect()
      el.removeEventListener("load", measure, true)
    }
  }, [isReply, editing, contentExpanded, comment.content])

  return (
    <div
      data-comment-id={comment.id}
      className={`group relative ${highlighted ? "outline outline-2 outline-primary/50 rounded-lg" : ""}`}
    >
      {/* Content and the footer chips share one press-feedback layer, since a
          reaction chip is also a long-press target — the whole comment reacts to
          the press. The long-press handlers live only on the content and the
          chips, though, so Reply and the composer aren't hijacked. */}
      <div
        className={`rounded-lg transition duration-[320ms] ${isPressing || highlight ? "scale-[0.99] bg-base-200" : ""}`}
      >
        <div className="touch-pan-y @mobile:select-none @mobile:touch-callout-none" {...(pressable ? longPress : {})}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <UserAvatar user={comment.user} size="medium" />
              <div className="text-xs flex items-center flex-wrap gap-y-1">
                <span className="font-semibold text-base-content">{comment.user.display_name}</span>
                {isNew && (
                  <span className="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase bg-primary/15 text-primary">
                    New
                  </span>
                )}
                <span className="text-base-500 ml-2">
                  <DateTime datetime={comment.created_at} format="contextual" />
                  {edited && <span className="ml-1">(edited)</span>}
                </span>
              </div>
            </div>
            {!editing && !isMobile && (
              <CommentMenu
                commentId={comment.id}
                canModify={canModify}
                onEdit={() => setEditing(true)}
                onDelete={() => void ctx.deleteComment(comment.id)}
              />
            )}
          </div>

          <div className="text-sm ml-7 mr-7 -mt-1">
            {editing ? (
              <CommentEditor
                initialContent={comment.content}
                workspaceId={ctx.workspaceId}
                submitOn="mod-enter"
                onSave={async (content, attachmentClaimId) => {
                  const result = await ctx.editComment(comment.id, content, { attachmentClaimId })
                  if (result) setEditing(false)
                  return result
                }}
                onCancel={() => setEditing(false)}
              />
            ) : (
              <>
                <div ref={contentRef} className={!isReply && !contentExpanded ? "line-clamp-4" : ""}>
                  <Markdown
                    source={stripPreviewedAttachmentLink(comment.content, comment.link_preview)}
                    variant="compact"
                  />
                </div>
                {isClamped && (
                  <button
                    type="button"
                    className="text-xs text-primary hover:underline mt-1"
                    onClick={() => setContentExpanded(v => !v)}
                  >
                    {contentExpanded ? "Show less" : "Show more"}
                  </button>
                )}
                {comment.link_preview && <CommentLinkPreview linkPreview={comment.link_preview} />}
              </>
            )}
          </div>
        </div>

        {!editing &&
          (isReply ? (
            <div className="ml-7 mt-1 flex items-center gap-1 flex-wrap">
              {/* On mobile the undecided "Decide" affordance and the add-reaction
                  menu move into the long-press sheet, mirroring chat; a decided
                  pill and the reaction chips stay visible. */}
              {(!isMobile || decision) && (
                <DecisionMarker decision={decision} onToggle={() => ctx.toggleDecision(comment.global_id)} />
              )}
              <ReactionBar
                reactions={comment.reactions}
                currentUserId={ctx.currentUserId}
                onToggle={type => ctx.toggleReaction(comment.id, type as ReactionType)}
                chipHandlers={pressable ? longPress : undefined}
                showMenu={!isMobile}
              />
            </div>
          ) : (
            // pb-4 is clearance for the replies connector, not visual spacing.
            <div className="mt-1 pb-4">
              <CommentActions
                comment={comment}
                workspaceId={ctx.workspaceId}
                currentUserId={ctx.currentUserId}
                decision={decision}
                onReply={(content, attachmentClaimId, unfurlLinks) =>
                  ctx.createComment(content, { parentId: comment.id, attachmentClaimId, unfurlLinks })
                }
                onToggleReaction={type => ctx.toggleReaction(comment.id, type as ReactionType)}
                onToggleDecision={() => ctx.toggleDecision(comment.global_id)}
                chipHandlers={pressable ? longPress : undefined}
              />
            </div>
          ))}
      </div>

      {!isReply && (
        <RepliesSection
          comment={comment}
          ctx={ctx}
          renderReply={reply => <Comment comment={reply} ctx={ctx} isReply />}
        />
      )}

      {sheetOpen && (
        <ActionSheet
          content={comment.content}
          author={comment.user}
          createdAt={comment.created_at}
          edited={edited}
          reactions={comment.reactions}
          isOwn={canModify}
          decision={decision}
          resourceLabel="comment"
          deleteConfirmation="Are you sure you want to delete this?"
          onClose={() => setSheetOpen(false)}
          onReact={reactionType => ctx.toggleReaction(comment.id, reactionType as ReactionType)}
          onEdit={() => setEditing(true)}
          onDelete={() => void ctx.deleteComment(comment.id)}
          onToggleDecision={() => ctx.toggleDecision(comment.global_id)}
        />
      )}
    </div>
  )
}
