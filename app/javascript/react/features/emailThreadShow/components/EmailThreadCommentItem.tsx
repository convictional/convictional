import { useCallback, useMemo, useState } from "react"

import { ActionSheet } from "~/react/composites/ActionSheet"
import { LinkPreviewCard } from "~/react/composites/chat/LinkPreviewCard"
import { replyContentPreview } from "~/react/composites/chat/replyPreview"
import { ReplyQuote } from "~/react/composites/comment/ReplyQuote"
import { DecisionMarker } from "~/react/composites/DecisionMarker"
import { Markdown } from "~/react/composites/markdown/Markdown"
import { ReactionChips } from "~/react/composites/reactions/ReactionChips"
import { Reactions } from "~/react/composites/reactions/Reactions"
import { stripPreviewedAttachmentLink } from "~/react/composites/stripAttachmentLink"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useLongPress } from "~/react/shared/hooks/useLongPress"
import { useScrollIntoViewOnEdit } from "~/react/shared/hooks/useScrollIntoViewOnEdit"
import { useSwipeReply } from "~/react/shared/hooks/useSwipeReply"
import { hasAnyReactions, type ReactionType } from "~/react/shared/reactions"
import type { Decision, LinkPreview, EmailThreadComment, ReplyPreview } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"
import { DateTime } from "~/react/ui/DateTime"

import { EmailThreadCommentEditor } from "./EmailThreadCommentEditor"
import { EmailThreadCommentMenu } from "./EmailThreadCommentMenu"

// Below this gap the timestamps are effectively the create-time write, so we
// only badge "(edited)" once a real follow-up edit lands.
const EDITED_THRESHOLD_MS = 10_000

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

interface EmailThreadCommentItemProps {
  comment: EmailThreadComment
  currentUserId: string | null
  workspaceId: string
  // The decision anchored to this comment, if any (resolved by the parent from
  // the comment's global_id). Undefined means the comment isn't a decision.
  decision: Decision | undefined
  // Flash this comment (deep-linked via `#comment-<id>`).
  highlighted: boolean
  // True when this comment continues a run from the same author (see Timeline):
  // drop the avatar and header, and reveal the timestamp/menu on hover.
  isGrouped?: boolean
  // Edit mode is controlled by the parent (EmailThreadShow owns the selection) so
  // the composer's Up-arrow can open a comment for editing.
  isEditing: boolean
  onStartEdit: (commentId: string) => void
  onEndEdit: () => void
  onEdit: (commentId: string, content: string, attachmentClaimId: string) => Promise<void>
  onDelete: (commentId: string) => Promise<void>
  onToggleReaction: (commentId: string, reactionType: ReactionType) => Promise<void>
  onToggleDecision: (commentGid: string) => Promise<void>
  // Open the composer's reply banner quoting this comment (builds the preview
  // from it). Available on desktop hover and in the mobile long-press sheet.
  onReply?: (preview: ReplyPreview) => void
  // Scroll to and flash a quoted comment, keyed by its id — backs the in-bubble
  // ReplyQuote's click-to-jump, which requires it for a live target.
  onScrollToComment: (commentId: string) => void
}

export function EmailThreadCommentItem({
  comment,
  currentUserId,
  workspaceId,
  decision,
  highlighted,
  isGrouped,
  isEditing,
  onStartEdit,
  onEndEdit,
  onEdit,
  onDelete,
  onToggleReaction,
  onToggleDecision,
  onReply,
  onScrollToComment,
}: EmailThreadCommentItemProps) {
  // Scroll a comment into view when it enters edit mode — the Up-arrow may open
  // one that's scrolled off-screen. `scroll-mb-24` on the root clears the sticky
  // bottom composer for the `block: "nearest"` alignment.
  const rootRef = useScrollIntoViewOnEdit<HTMLDivElement>(isEditing)

  // On touch there's no hover, so a long-press opens an action sheet holding
  // every action (react/decide/copy/edit/delete) instead of the hover-revealed
  // inline affordances, mirroring chat's InteractiveMessageBubble.
  const isMobile = useIsMobile()
  const [showActionSheet, setShowActionSheet] = useState(false)
  const { handlers: longPress, isPressing, highlight } = useLongPress(useCallback(() => setShowActionSheet(true), []))

  const wasEdited =
    new Date(comment.updated_at).getTime() - new Date(comment.created_at).getTime() > EDITED_THRESHOLD_MS
  const isAuthor = currentUserId !== null && currentUserId === comment.user?.id

  // A grouped continuation always drops its avatar for a tight run (keyed on
  // isGrouped alone, so it stays aligned with the negative margin Timeline
  // applies on the same flag). Its header is only revealed when the comment was
  // edited, so the "(edited)" badge stays visible.
  const collapsed = Boolean(isGrouped) && !wasEdited

  const menu = isAuthor ? (
    <EmailThreadCommentMenu onEdit={() => onStartEdit(comment.id)} onDelete={() => onDelete(comment.id)} />
  ) : null

  // Optimistic reply preview shown in the compose banner before the send lands;
  // the server returns the same shape as the posted reply's reply_to.
  const onReplyBound = useCallback(
    () =>
      onReply?.({
        id: comment.id,
        user_name: comment.user?.display_name ?? "",
        content_preview: replyContentPreview(comment.content),
        is_deleted: false,
      }),
    [onReply, comment.id, comment.user?.display_name, comment.content]
  )

  // Left-swipe-to-reply on touch: only when replying is available, and it coexists
  // with the long-press action sheet on the same element (a swipe's horizontal
  // movement cancels the press). The swipe binds its own native listeners through
  // its ref, merged with rootRef.
  const swipeEnabled = isMobile && Boolean(onReply)
  const {
    ref: swipeRef,
    offset: swipeOffset,
    progress: swipeProgress,
    armed: swipeArmed,
    swiping: isSwiping,
    onClickCapture: onSwipeClickCapture,
  } = useSwipeReply({ enabled: swipeEnabled, onReply: onReplyBound })
  const setRootRef = useCallback(
    (node: HTMLDivElement | null) => {
      rootRef.current = node
      swipeRef(node)
    },
    [rootRef, swipeRef]
  )

  // A bare comment shows no footer at all, so a run of comments stays tight
  // instead of stranding a "Decide" affordance between them. The Decide + react
  // actions move beside the bubble, revealed on hover. Once a comment is decided
  // or reacted-to, the footer becomes persistent.
  const showFooter = decision !== undefined || hasAnyReactions(comment.reactions)

  // Re-render the markdown only when the content changes — this lives in a
  // timeline list where parent re-renders are frequent.
  const body = useMemo(
    () => <Markdown source={stripPreviewedAttachmentLink(comment.content, comment.link_preview)} variant="compact" />,
    [comment.content, comment.link_preview]
  )

  return (
    <div
      // Skip the swipe ref while editing: the editor renders inside this root, so
      // a live swipe would preventDefault the textarea's own caret/selection
      // gestures and, on commit, discard the unsaved edit. The hook binds its
      // native listeners once when the ref attaches, so swapping the ref (rather
      // than gating `enabled`) is what actually tears them down.
      ref={isEditing ? rootRef : setRootRef}
      className={`group relative scroll-mb-24 touch-pan-y @mobile:select-none @mobile:touch-callout-none transition-transform duration-[320ms] ${
        isPressing || highlight ? "scale-[0.99]" : ""
      } ${highlighted ? "outline outline-2 outline-primary/50 rounded-lg" : ""}`}
      data-comment-id={comment.id}
      onClickCapture={onSwipeClickCapture}
      {...(isEditing ? {} : longPress)}
    >
      {/* Reply affordance revealed behind the row as it's pulled left. It arms
          (fills to a solid primary disc) once the trigger distance is crossed. */}
      {swipeOffset < 0 && (
        <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none" aria-hidden="true">
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-full transition-colors duration-150 ${
              swipeArmed ? "bg-primary text-primary-content" : "bg-base-300 text-base-content/50"
            }`}
            style={{
              opacity: Math.min(1, swipeProgress + 0.25),
              transform: `scale(${swipeArmed ? 1 : 0.6 + swipeProgress * 0.4})`,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              reply
            </span>
          </div>
        </div>
      )}
      <div
        className={isSwiping ? "" : "transition-transform duration-[220ms] ease-out"}
        // Only carry the transform where a swipe can happen; skip it on desktop so
        // every row isn't promoted to its own compositing layer for no benefit.
        style={swipeEnabled ? { transform: `translate3d(${swipeOffset}px, 0, 0)` } : undefined}
      >
        <div className="flex gap-2 items-start">
          {isGrouped ? (
            <div className="w-6 h-6 shrink-0" />
          ) : (
            comment.user && (
              <Avatar picture={comment.user.picture} displayName={comment.user.display_name} size="medium" />
            )
          )}
          <div className="flex-1 min-w-0">
            {!collapsed && (
              <div className="flex items-center gap-2 text-xs text-base-500">
                {comment.user && <span className="font-semibold text-base-content">{comment.user.display_name}</span>}
                <DateTime datetime={comment.created_at} />
                {wasEdited && <span className="text-base-400">(edited)</span>}
                {!isMobile && menu && <div className="ml-auto">{menu}</div>}
              </div>
            )}
            {isEditing ? (
              <EmailThreadCommentEditor
                comment={comment}
                workspaceId={workspaceId}
                onSave={async (content, attachmentClaimId) => {
                  await onEdit(comment.id, content, attachmentClaimId)
                  onEndEdit()
                }}
                onCancel={onEndEdit}
              />
            ) : (
              <>
                <div className="flex items-start gap-1">
                  <div className="mt-0.5 w-fit min-w-0 max-w-full rounded-xl bg-base-200 px-3 py-1.5 text-sm text-base-content break-words">
                    {comment.reply_to && <ReplyQuote replyTo={comment.reply_to} onScrollTo={onScrollToComment} />}
                    {body}
                    {comment.link_preview && (
                      <div className="mt-2 max-w-lg">
                        <LinkPreviewCard
                          linkPreview={
                            {
                              ...comment.link_preview,
                              type: "link",
                              site_name: null,
                              domain: domainOf(comment.link_preview.url),
                            } satisfies LinkPreview
                          }
                        />
                      </div>
                    )}
                    {comment.attachments.length > 0 && (
                      <ul className="mt-1 text-sm">
                        {comment.attachments
                          .filter(a => a.show_in_list)
                          .map(a => (
                            <li key={a.id} className="py-1 flex items-center gap-1">
                              {/* Same-origin file download: opt out of HTMX boost so the
                                  browser downloads it instead of AJAX-swapping the bytes. */}
                              <a
                                href={a.download_url}
                                className="flex items-center gap-1 hover:underline"
                                data-hx-boost="false"
                              >
                                <span className="material-symbols-outlined text-sm">attach_file</span>
                                <span>{a.filename}</span>
                              </a>
                            </li>
                          ))}
                      </ul>
                    )}
                  </div>
                  {/* Reply always beside the bubble; Decide + react join it only for a
                  bare comment (a decided/reacted comment surfaces those in its
                  footer). Width, not height, and hover-revealed on desktop so
                  grouped runs stay tight. Mobile has no hover — these all live in
                  the long-press sheet instead. */}
                  {!isMobile && (onReply || !showFooter) && (
                    <div className="mt-0.5 flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      {onReply && (
                        <button
                          type="button"
                          onClick={onReplyBound}
                          className="btn btn-sm btn-ghost btn-square"
                          aria-label="Reply"
                        >
                          <span className="material-symbols-outlined text-base">reply</span>
                        </button>
                      )}
                      {!showFooter && (
                        <>
                          <DecisionMarker decision={undefined} onToggle={() => onToggleDecision(comment.global_id)} />
                          <Reactions
                            reactions={comment.reactions}
                            currentUserId={currentUserId}
                            onToggle={reactionType => onToggleReaction(comment.id, reactionType)}
                          />
                        </>
                      )}
                    </div>
                  )}
                </div>
                {showFooter && (
                  <div className="flex items-center gap-1 flex-wrap">
                    {/* Reactions carries its own mt-1; match it on the marker so the pill
                    sits on the same baseline as the chips on this shared row. On mobile
                    the undecided marker and add-reaction trigger live in the long-press
                    sheet, so the footer shows only a decided marker + the chip strip. */}
                    {(!isMobile || decision !== undefined) && (
                      <DecisionMarker
                        className="mt-1"
                        decision={decision}
                        onToggle={() => onToggleDecision(comment.global_id)}
                      />
                    )}
                    {isMobile ? (
                      <div className="mt-1 flex items-center gap-1 flex-wrap">
                        <ReactionChips
                          reactions={comment.reactions}
                          currentUserId={currentUserId}
                          onToggle={reactionType => onToggleReaction(comment.id, reactionType)}
                        />
                      </div>
                    ) : (
                      <Reactions
                        reactions={comment.reactions}
                        currentUserId={currentUserId}
                        onToggle={reactionType => onToggleReaction(comment.id, reactionType)}
                      />
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
        {/* Collapsed runs have no header, so surface the timestamp + author menu
            in the top-right — the run's create-time write is otherwise hidden.
            The menu hover-reveals on desktop; on mobile it moves into the long-press
            sheet, so only the timestamp stays (always visible, no hover to reveal it). */}
        {collapsed && !isEditing && (
          <div className="absolute right-2 top-0 flex items-center gap-2 text-xs text-base-500">
            <DateTime
              datetime={comment.created_at}
              className={isMobile ? undefined : "opacity-0 transition-opacity group-hover:opacity-100"}
            />
            {!isMobile && menu}
          </div>
        )}
      </div>
      {showActionSheet && (
        <ActionSheet
          content={comment.content}
          author={comment.user}
          createdAt={comment.created_at}
          edited={wasEdited}
          reactions={comment.reactions}
          isOwn={isAuthor}
          decision={decision}
          resourceLabel="comment"
          deleteConfirmation="Are you sure you want to delete this comment?"
          onClose={() => setShowActionSheet(false)}
          onReact={reactionType => onToggleReaction(comment.id, reactionType as ReactionType)}
          onReply={onReply ? onReplyBound : undefined}
          onEdit={() => onStartEdit(comment.id)}
          onDelete={() => onDelete(comment.id)}
          onToggleDecision={() => onToggleDecision(comment.global_id)}
        />
      )}
    </div>
  )
}
