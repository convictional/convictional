import { memo, useCallback, useState } from "react"

import { ActionSheet } from "~/react/composites/ActionSheet"
import { replyContentPreview } from "~/react/composites/chat/replyPreview"
import { DecisionMarker } from "~/react/composites/DecisionMarker"
import { ReactionChips } from "~/react/composites/reactions/ReactionChips"
import { ReactionMenu } from "~/react/composites/reactions/ReactionMenu"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useLongPress } from "~/react/shared/hooks/useLongPress"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import { useScrollIntoViewOnEdit } from "~/react/shared/hooks/useScrollIntoViewOnEdit"
import { useSwipeReply } from "~/react/shared/hooks/useSwipeReply"
import { hasAnyReactions } from "~/react/shared/reactions"
import type { ChatMessage, ChatType, Decision, ReplyPreview } from "~/react/shared/types"
import { ChatImage } from "~/react/ui/ChatImage"
import { ChatImageGallery } from "~/react/ui/ChatImageGallery"
import { DateTime } from "~/react/ui/DateTime"
import { EditMessageForm } from "./EditMessageForm"
import { MessageActions } from "./MessageActions"
import { MessageBubble as SharedMessageBubble } from "./MessageBubble"

// Callbacks take `messageId` (and content / reactionType / preview where
// applicable) so the parent can pass stable references down through `messages.map`
// without rebinding per-message. That stability is what lets the surrounding
// `React.memo` actually skip re-renders when sibling state (e.g. autoScroll)
// flips — see ChatShow's MessageList integration.
interface MessageBubbleProps {
  message: ChatMessage
  className?: string
  currentUserId: string
  isGrouped?: boolean
  isEditing: boolean
  isCompact?: boolean
  chatType: ChatType
  uploadUrl: string | null
  mentionableUsers: MentionUser[]
  mentionsEnabled?: boolean
  klipyApiKey: string | null
  onScrollTo: (targetId: string) => void
  scrollingToId: string | null
  onEdit: (messageId: string) => void
  onCancelEdit: () => void
  onSaveEdit: (
    messageId: string,
    content: string,
    attachmentClaimId: string | null,
    retainedAttachmentIds: string[]
  ) => Promise<void>
  onDelete: (messageId: string) => void
  onReact: (messageId: string, reactionType: string) => void
  onReply: (preview: ReplyPreview) => void
  decision?: Decision
  onToggleDecision?: (commentGid: string) => void
}

function InteractiveMessageBubbleImpl({
  message,
  className,
  currentUserId,
  isGrouped,
  isEditing,
  isCompact,
  chatType,
  uploadUrl,
  mentionableUsers,
  mentionsEnabled,
  klipyApiKey,
  onScrollTo,
  scrollingToId,
  onEdit,
  onCancelEdit,
  onSaveEdit,
  onDelete,
  onReact,
  onReply,
  decision,
  onToggleDecision,
}: MessageBubbleProps) {
  const isOwn = message.user.id === currentUserId
  const hasReactions = hasAnyReactions(message.reactions)
  const [showActionSheet, setShowActionSheet] = useState(false)
  // isPressing drives the press-in shrink; highlight pops the bubble's tone just
  // before the trigger to emphasize "this one". Both are timed inside the hook.
  const { handlers: longPress, isPressing, highlight } = useLongPress(useCallback(() => setShowActionSheet(true), []))
  const editingWrapperRef = useScrollIntoViewOnEdit<HTMLDivElement>(isEditing)

  const messageId = message.id
  const onEditBound = useCallback(() => onEdit(messageId), [onEdit, messageId])
  const onDeleteBound = useCallback(() => onDelete(messageId), [onDelete, messageId])
  const onReactBound = useCallback((reactionType: string) => onReact(messageId, reactionType), [onReact, messageId])
  const onSaveEditBound = useCallback(
    (content: string, attachmentClaimId: string | null, retainedAttachmentIds: string[]) =>
      onSaveEdit(messageId, content, attachmentClaimId, retainedAttachmentIds),
    [onSaveEdit, messageId]
  )
  const onReplyBound = useCallback(
    () =>
      onReply({
        id: messageId,
        user_name: message.user.display_name,
        content_preview: replyContentPreview(message.content),
        is_deleted: false,
      }),
    [onReply, messageId, message.user.display_name, message.content]
  )

  const messageGid = message.global_id
  const onToggleDecisionBound = useCallback(() => onToggleDecision?.(messageGid), [onToggleDecision, messageGid])

  // Swipe a message left to reply, mirroring the inbox's swipe affordance. Touch
  // only; coexists with the long-press handlers on the same element (a swipe's
  // movement cancels the press via longPress.onTouchMove, a still hold still
  // opens the action sheet). The swipe binds its own native listeners through its ref.
  const isMobile = useIsMobile()
  const {
    ref: swipeRef,
    offset: swipeOffset,
    progress: swipeProgress,
    armed: swipeArmed,
    swiping: isSwiping,
    onClickCapture: onSwipeClickCapture,
  } = useSwipeReply({ enabled: isMobile, onReply: onReplyBound })

  // Footer shown for any decided/reacted message; a bare message has none. The
  // marker, add-reaction menu, and chips are flat siblings (not nested under a
  // ReactionBar) so the strip wraps as one sequence instead of stranding the
  // pill on its own row when the chips overflow to a second line.
  //
  // On mobile the marker is decided-only and the add-menu is hidden: the
  // undecided "Decide" action and adding reactions both live in the long-press
  // overlay, so the footer never shows a stray "Decide" badge or inline `+`.
  const showFooter = decision !== undefined || hasReactions
  const showDecisionMarker = onToggleDecision && (!isMobile || decision !== undefined)
  const showAddMenu = !isMobile && hasReactions
  const footer = showFooter && (
    <div className="flex flex-wrap items-center gap-1 @mobile:gap-1.5 ml-8 mt-0.5">
      {showDecisionMarker && <DecisionMarker decision={decision} onToggle={onToggleDecisionBound} />}
      {showAddMenu && <ReactionMenu onSelect={onReactBound} />}
      <ReactionChips reactions={message.reactions} currentUserId={currentUserId} onToggle={onReactBound} />
    </div>
  )

  if (isEditing) {
    return (
      <div
        ref={editingWrapperRef}
        id={`chat-message-${message.id}`}
        className={`group scroll-mb-24 ${className ?? ""}`}
      >
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            <SharedMessageBubble
              message={message}
              isGrouped={isGrouped}
              onScrollTo={onScrollTo}
              scrollingToId={scrollingToId}
              replaceBubble={
                <div className="flex-1 min-w-0">
                  <EditMessageForm
                    initialContent={message.content}
                    chatType={chatType}
                    uploadUrl={uploadUrl}
                    mentionableUsers={mentionableUsers}
                    mentionsEnabled={mentionsEnabled}
                    klipyApiKey={klipyApiKey}
                    onSave={onSaveEditBound}
                    onCancel={onCancelEdit}
                  />
                </div>
              }
            />
          </div>
          {!isCompact && (
            <DateTime
              datetime={message.created_at}
              format="contextual"
              className="text-xs min-w-max self-start pt-1.5 hidden sm:block text-base-content/50"
            />
          )}
        </div>
        {footer}
      </div>
    )
  }

  const groupedTimestampClass = isGrouped ? "opacity-0 group-hover:opacity-100 transition-opacity" : ""

  // duration matches the hook's press-to-trigger window (threshold minus the
  // start delay) so the shrink lands exactly at the trigger inflection.
  return (
    <div
      ref={swipeRef}
      id={`chat-message-${message.id}`}
      className={`group relative min-w-0 touch-pan-y @mobile:select-none @mobile:touch-callout-none transition-transform duration-[320ms] ${
        isPressing || highlight ? "scale-[0.97]" : ""
      } ${className ?? ""}`}
      onClickCapture={onSwipeClickCapture}
      {...longPress}
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
        style={{ transform: `translate3d(${swipeOffset}px, 0, 0)` }}
      >
        <SharedMessageBubble
          message={message}
          isGrouped={isGrouped}
          highlight={highlight}
          onScrollTo={onScrollTo}
          scrollingToId={scrollingToId}
          afterBubble={
            <>
              <MessageActions
                isOwn={isOwn}
                hasReactions={hasReactions}
                isCompact={isCompact}
                onReact={onReactBound}
                onReply={onReplyBound}
                onEdit={onEditBound}
                onDelete={onDeleteBound}
                // No footer to host the marker → the toolbar carries Decide instead.
                onToggleDecision={onToggleDecision && !showFooter ? onToggleDecisionBound : undefined}
              />
              {!isCompact && (
                <DateTime
                  datetime={message.created_at}
                  format="contextual"
                  className={`text-xs ml-auto min-w-max self-start pt-1.5 hidden sm:block text-base-content/50 ${groupedTimestampClass}`}
                />
              )}
            </>
          }
        >
          {!isGrouped && (
            <DateTime
              datetime={message.created_at}
              format="contextual"
              className={`text-xs text-base-500/70 float-right ${isCompact ? "" : "sm:hidden"}`}
            />
          )}
        </SharedMessageBubble>
        {footer}
      </div>
      {showActionSheet && (
        <ActionSheet
          content={message.content}
          author={message.user}
          createdAt={message.created_at}
          edited={Boolean(message.edited_at)}
          reactions={message.reactions}
          isOwn={isOwn}
          decision={decision}
          onClose={() => setShowActionSheet(false)}
          onReact={onReactBound}
          onReply={onReplyBound}
          onEdit={onEditBound}
          onDelete={onDeleteBound}
          onToggleDecision={onToggleDecision ? onToggleDecisionBound : undefined}
          imageComponent={ChatImage}
          imageGroupComponent={ChatImageGallery}
        />
      )}
    </div>
  )
}

export const InteractiveMessageBubble = memo(InteractiveMessageBubbleImpl)
