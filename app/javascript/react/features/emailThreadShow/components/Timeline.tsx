import { Fragment, useMemo, useState } from "react"

import { UnreadDivider } from "~/react/composites/UnreadDivider"
import type { ReactionType } from "~/react/shared/reactions"
import type { Decision, ReplyPreview, TimelineItem, EmailThreadComment } from "~/react/shared/types"

import { computeCollapsedGroup, mergeTimeline, type MergedEntry } from "../collapsedGroup"
import { ActivityEvent } from "./ActivityEvent"
import { CollapsedGroupBar } from "./CollapsedGroupBar"
import { EmailMessage } from "./EmailMessage"
import { EmailThreadCommentItem } from "./EmailThreadCommentItem"

interface TimelineProps {
  items: TimelineItem[]
  comments: EmailThreadComment[]
  // Caller flags which messages should render collapsed at mount. The set is
  // typically derived from the thread's read state.
  collapsedMessageIds: Set<string>
  canReply: boolean
  isSuperuser: boolean
  currentUserEmail: string | null
  currentUserId: string | null
  workspaceId: string
  // comment_gid -> decision, for the inline DecisionMarker on internal comments.
  decisionsByGid: Map<string, Decision>
  // Comment id to flash (deep link via `#comment-<id>`), or null.
  highlightedCommentId: string | null
  // The comment currently open for inline editing (owned by EmailThreadShow so the
  // composer's Up-arrow can drive it), plus the callbacks to enter/leave edit mode.
  editingCommentId: string | null
  onStartEditComment: (commentId: string) => void
  onEndEditComment: () => void
  // The initial-scroll target (derived by the parent) and the callback ref to wire
  // onto it. Timeline only attaches the ref to the matching message; it owns no
  // scroll policy.
  scrollTargetId?: string | null
  scrollTargetRef?: (node: HTMLElement | null) => void
  // The first unread item's id (message or comment). The read run before it is
  // compacted into a Gmail-style collapsed group (see collapsedGroup.ts); null
  // when nothing is unread or the run is too short to be worth compacting.
  collapseBoundaryId?: string | null
  // The first unread comment drives the "N new comments" divider rendered just
  // before it; null means no divider. unreadCommentCount is the divider's label.
  firstUnreadCommentId: string | null
  unreadCommentCount: number
  // Handlers take the message id directly — Timeline passes its props
  // straight through to each EmailMessage without re-allocating closures, so
  // EmailMessage can be safely memoized.
  onReply: (messageId: string) => void
  onReplyAll: (messageId: string) => void
  onForward: (messageId: string) => void
  onEditComment: (commentId: string, content: string, attachmentClaimId: string) => Promise<void>
  onDeleteComment: (commentId: string) => Promise<void>
  onToggleReaction: (commentId: string, reactionType: ReactionType) => Promise<void>
  // Single-click decision toggle, keyed by the comment's global_id.
  onToggleDecision: (commentGid: string) => Promise<void>
  // Open the composer's reply banner quoting a comment, and scroll-to-quote for
  // the in-bubble ReplyQuote. Both flow straight through to EmailThreadCommentItem.
  onReplyToComment: (preview: ReplyPreview) => void
  onScrollToComment: (commentId: string) => void
}

// Flat, chronologically ordered list. Branches on `item.type` to render
// either an EmailMessage or an ActivityEvent. The parent supplies the
// pre-sorted items; sorting here would re-sort on every render and lose
// the stable order the channel handlers append in.
export function Timeline({
  items,
  comments,
  collapsedMessageIds,
  canReply,
  isSuperuser,
  currentUserEmail,
  currentUserId,
  workspaceId,
  decisionsByGid,
  highlightedCommentId,
  editingCommentId,
  onStartEditComment,
  onEndEditComment,
  scrollTargetId,
  scrollTargetRef,
  collapseBoundaryId,
  firstUnreadCommentId,
  unreadCommentCount,
  onReply,
  onReplyAll,
  onForward,
  onEditComment,
  onDeleteComment,
  onToggleReaction,
  onToggleDecision,
  onReplyToComment,
  onScrollToComment,
}: TimelineProps) {
  const merged = useMemo(() => mergeTimeline(items, comments), [items, comments])

  const lastMessageId = useMemo(() => {
    for (let i = items.length - 1; i >= 0; i--) {
      const item = items[i]
      if (item.type === "message") return item.message.id
    }
    return null
  }, [items])

  const group = useMemo(() => computeCollapsedGroup(merged, collapseBoundaryId ?? null), [merged, collapseBoundaryId])
  // Whether the collapsed group's hidden middle has been revealed. One-way: like
  // Gmail, clicking the bar expands the run to previews and there's no re-collapse.
  const [stackExpanded, setStackExpanded] = useState(false)

  // Stable key for a merged entry, matching the ids renderEntry keys its own output with.
  const entryKey = (entry: MergedEntry) =>
    entry.kind === "comment" ? `comment-${entry.comment.id}` : `item-${entry.item.item_id}`

  // inGroup renders messages without their own border so they sit as rows inside the
  // collapsed group's single bordered container. disableGrouping drops the same-author
  // negative top margin: peekBottom's rendered predecessor while the stack is collapsed is
  // the count bar, not its same-author comment, so the -mt-3.5 would pull it up over the bar.
  const renderEntry = (entry: MergedEntry, inGroup = false, disableGrouping = false) => {
    if (entry.kind === "comment") {
      const isDivider = firstUnreadCommentId != null && entry.comment.id === firstUnreadCommentId
      // A divider (or a hidden predecessor behind the count bar) between this comment and the
      // previous one breaks the grouping run.
      const grouped = isDivider || disableGrouping ? false : entry.isGrouped
      return (
        <Fragment key={`comment-${entry.comment.id}`}>
          {isDivider && <UnreadDivider count={unreadCommentCount} noun="comment" />}
          {/* Inside the group card there's no parent gap, so a bubble needs its own vertical
              padding; grouped continuations keep the -mt-3.5 tuck and only pad below. */}
          <div className={grouped ? `px-4 -mt-3.5${inGroup ? " pb-2" : ""}` : `px-4${inGroup ? " py-2" : ""}`}>
            <EmailThreadCommentItem
              comment={entry.comment}
              currentUserId={currentUserId}
              workspaceId={workspaceId}
              decision={decisionsByGid.get(entry.comment.global_id)}
              highlighted={entry.comment.id === highlightedCommentId}
              isGrouped={grouped}
              isEditing={entry.comment.id === editingCommentId}
              onStartEdit={onStartEditComment}
              onEndEdit={onEndEditComment}
              onEdit={onEditComment}
              onDelete={onDeleteComment}
              onToggleReaction={onToggleReaction}
              onToggleDecision={onToggleDecision}
              onReply={onReplyToComment}
              onScrollToComment={onScrollToComment}
            />
          </div>
        </Fragment>
      )
    }
    const item = entry.item
    if (item.type === "message") {
      const messageId = item.message.id
      return (
        <EmailMessage
          key={`message-${item.item_id}`}
          ref={messageId === scrollTargetId ? scrollTargetRef : undefined}
          message={item.message}
          isLastMessage={messageId === lastMessageId}
          canReply={canReply}
          isSuperuser={isSuperuser}
          startCollapsed={collapsedMessageIds.has(messageId)}
          inGroup={inGroup}
          currentUserEmail={currentUserEmail}
          onReply={onReply}
          onReplyAll={onReplyAll}
          onForward={onForward}
        />
      )
    }
    return (
      <div key={`event-${item.item_id}`} className="px-4">
        <ActivityEvent event={item.event} />
      </div>
    )
  }

  // The parent supplies the layout container with gap-4 px-2 spacing.
  // Timeline only owns the per-item branching. A wrapper here would
  // override the parent gap and visibly pull items closer together.
  //
  // When a collapsed group exists, its read run renders as one bordered container
  // (the two peeked messages with the count bar, or the revealed previews, between
  // them), then the rest of the thread from the boundary item onward renders normally.
  if (!group) {
    return <>{merged.map(entry => renderEntry(entry))}</>
  }

  // A hairline separates the group's rows, but never between two chat bubbles: a
  // divider drawn behind a run of bubbles reads as a stray line (and a grouped
  // comment's -mt-3.5 tuck would cross it). So it's drawn above every row except
  // the first and except a chat that follows another chat — leaving a clean line
  // around the email rows and above the first chat of a cluster. A blanket
  // `divide-y` can't express that, so the separator is placed per row here.
  const groupRow = (entry: MergedEntry, prev: MergedEntry | undefined) => {
    const separated = prev != null && !(entry.kind === "comment" && prev.kind === "comment")
    return (
      <div key={entryKey(entry)} className={separated ? "border-t border-base-300" : undefined}>
        {renderEntry(entry, true)}
      </div>
    )
  }

  const runRows = stackExpanded ? [group.peekTop, ...group.hidden, group.peekBottom] : null

  return (
    <>
      <div className="bg-base-50 border rounded-xl overflow-hidden border-base-300 shadow-xs">
        {runRows ? (
          runRows.map((entry, i) => groupRow(entry, runRows[i - 1]))
        ) : (
          <>
            {renderEntry(group.peekTop, true)}
            <div className="border-t border-base-300">
              <CollapsedGroupBar
                emailCount={group.hiddenEmailCount}
                chatCount={group.hiddenChatCount}
                onExpand={() => setStackExpanded(true)}
              />
            </div>
            <div className="border-t border-base-300">{renderEntry(group.peekBottom, true, true)}</div>
          </>
        )}
      </div>
      {merged.slice(group.runLength).map(entry => renderEntry(entry))}
    </>
  )
}
