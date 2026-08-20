import { useMemo, useState } from "react"

import type { EmailThreadShowResponse } from "~/react/shared/types"

import { computeCollapsedGroup, mergeTimeline } from "../collapsedGroup"
import { firstUnreadMessageId, lastMessageId, unreadComments } from "../readState"

export type ReadCursor = { readAt: string | null; isUnread: boolean }

export interface InitialScrollTarget {
  scrollKey: string | null
  messageScrollTargetId: string | null
  commentScrollTargetId: string | null
  readCursor: ReadCursor | null
  // Whether the read run before the boundary is long enough to compact into the
  // Gmail-style collapsed group. Derived from the SAME frozen snapshot as the scroll
  // targets so the scroll-suppression decision is latched at load: a later refetch (which
  // may delete a comment out of the run, or re-mark the thread read) can't flip it and
  // re-fire the "initial" scroll after the fact. Timeline recomputes the group over live
  // data for rendering; only the scroll decision is frozen here.
  hasCollapsedGroup: boolean
}

// Decides the initial scroll target from the FIRST-loaded thread snapshot and freezes it
// against refetch. EmailThreadShow's refetch() (WS reconnect rehydrate, workspace-event
// refresh) replaces `data` with the current server state; because opening the thread marks it
// read, that fresh snapshot flips read_at from null to a timestamp. Deriving the scroll key /
// target from the live `data` would then change the key mid-read and re-fire the "initial"
// scroll (useInitialThreadScroll re-keys its callback ref on scrollKey) — throwing a reader
// back to the top of a long email (#8838). So we latch the snapshot on the first load for a
// thread and derive everything from it; a different threadId (a remount in practice) re-latches.
export function useInitialScrollTarget(
  threadId: string,
  data: EmailThreadShowResponse | null,
  currentUserId: string | null
): InitialScrollTarget {
  // Latch the first-loaded snapshot for this thread via a render-phase state update (React's
  // sanctioned "store info from previous renders" pattern). Holding it in state keeps a stable
  // identity for the memo below and re-latches when threadId changes; the guard makes the
  // update a no-op once latched, so it doesn't loop.
  const [frozen, setFrozen] = useState<{ threadId: string; data: EmailThreadShowResponse } | null>(null)
  if (data && frozen?.threadId !== threadId) {
    setFrozen({ threadId, data })
  }
  const snapshot = frozen?.threadId === threadId ? frozen.data : null

  return useMemo(() => {
    if (!snapshot) {
      return {
        scrollKey: null,
        messageScrollTargetId: null,
        commentScrollTargetId: null,
        readCursor: null,
        hasCollapsedGroup: false,
      }
    }
    const { read_at: readAt, is_unread: isUnread } = snapshot.mailbox_entry
    const readCursor: ReadCursor = { readAt, isUnread }
    const scrollKey = `${threadId}:${readAt ?? "unread"}`

    // Land on the earliest unread item. Messages and comments scroll by different mechanisms
    // (see EmailThreadShow) and only one target fires.
    const unreadMessageId = firstUnreadMessageId(snapshot.timeline, readAt, isUnread)
    const firstComment = unreadComments(snapshot.comments, readAt, isUnread, currentUserId)[0] ?? null

    let messageScrollTargetId: string | null = null
    let commentScrollTargetId: string | null = null
    if (unreadMessageId && firstComment) {
      const message = snapshot.timeline.find(i => i.type === "message" && i.message.id === unreadMessageId)
      // Compare numerically to match Timeline's own created_at ordering; string comparison
      // would disagree across mixed timestamp formats/offsets.
      const messageFirst =
        !message || new Date(message.created_at).getTime() <= new Date(firstComment.created_at).getTime()
      if (messageFirst) messageScrollTargetId = unreadMessageId
      else commentScrollTargetId = firstComment.id
    } else if (unreadMessageId) {
      messageScrollTargetId = unreadMessageId
    } else if (firstComment) {
      commentScrollTargetId = firstComment.id
    } else {
      // A fully-read thread top-aligns the newest message.
      messageScrollTargetId = lastMessageId(snapshot.timeline)
    }

    // The boundary is whichever target renders expanded first; the read run before it is what
    // the collapsed group compacts. Computed from the frozen snapshot so the decision is
    // latched (see hasCollapsedGroup above) and matches Timeline's group at load time.
    const boundaryId = messageScrollTargetId ?? commentScrollTargetId
    const hasCollapsedGroup =
      computeCollapsedGroup(mergeTimeline(snapshot.timeline, snapshot.comments), boundaryId) !== null

    return { scrollKey, messageScrollTargetId, commentScrollTargetId, readCursor, hasCollapsedGroup }
  }, [snapshot, threadId, currentUserId])
}
