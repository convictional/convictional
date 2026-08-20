import type { EmailMessageSummary, EmailThreadComment, TimelineItem } from "~/react/shared/types"

// Pure timeline/read-state helpers shared by EmailThreadShow (collapse + unread divider) and
// useInitialScrollTarget (the initial scroll target). Kept in their own module so the hook and
// the component can both import them without a circular dependency.

// Whether an ISO timestamp precedes the mailbox's last-read moment. Shared by the
// message and comment read tests so both agree on the boundary and NaN handling.
function arrivedBeforeRead(isoTimestamp: string, readAtMs: number): boolean {
  const resolvedMs = Date.parse(isoTimestamp)
  return !Number.isNaN(readAtMs) && !Number.isNaN(resolvedMs) && resolvedMs < readAtMs
}

function messageArrivedBeforeRead(message: EmailMessageSummary, readAtMs: number): boolean {
  return arrivedBeforeRead(message.received_at ?? message.created_at, readAtMs)
}

export function collapsedMessageIdsFor(
  timeline: TimelineItem[],
  readAt: string | null,
  isUnread: boolean
): Set<string> {
  // Which messages start collapsed is purely a client decision: a read message
  // starts collapsed unless it's the most recent message in the thread, which
  // always starts expanded. A message counts as read when the whole thread has
  // been read (is_unread === false) OR it arrived before the mailbox was last read
  // (read_at) — the read_at branch keeps a newly-arrived message on an otherwise-read
  // thread expanded. Relying on read_at alone wrongly expands everything for a thread
  // that's read but has no read_at timestamp. Explicitly marking a thread unread clears
  // read_at (server-side and optimistically here), so the unread branch then expands every
  // message. The server is agnostic to all of this —
  // the timeline embeds no bodies and every one loads lazily on expand.
  const readAtMs = readAt ? Date.parse(readAt) : NaN
  let lastMessageId: string | null = null
  for (let i = timeline.length - 1; i >= 0; i--) {
    const item = timeline[i]
    if (item.type === "message") {
      lastMessageId = item.message.id
      break
    }
  }
  const collapsed = new Set<string>()
  for (const item of timeline) {
    if (item.type !== "message") continue
    if (item.message.id === lastMessageId) continue
    const arrivedBeforeRead = messageArrivedBeforeRead(item.message, readAtMs)
    if (!isUnread || arrivedBeforeRead) {
      collapsed.add(item.message.id)
    }
  }
  return collapsed
}

// The oldest unread message in display order, or null when nothing is unread —
// the caller then falls back to lastMessageId for the initial scroll target.
// "Unread" reuses collapsedMessageIdsFor's read test (received_at ?? created_at vs
// read_at), so a thread that's unread only via a backchannel comment returns null
// here too (and lands on the newest message rather than the comment).
export function firstUnreadMessageId(
  timeline: TimelineItem[],
  readAt: string | null,
  isUnread: boolean
): string | null {
  if (!isUnread) return null
  const readAtMs = readAt ? Date.parse(readAt) : NaN
  for (const item of timeline) {
    if (item.type !== "message") continue
    if (!messageArrivedBeforeRead(item.message, readAtMs)) return item.message.id
  }
  return null
}

// Comments newer than the last read, authored by someone other than the viewer,
// in display (created_at) order. Mirrors firstUnreadMessageId's read test and
// is-unread gate. Own comments are excluded so a comment you just posted never
// raises a divider above itself — unlike email messages, comments are authored
// in-app by the viewer.
export function unreadComments(
  comments: EmailThreadComment[],
  readAt: string | null,
  isUnread: boolean,
  currentUserId: string | null
): EmailThreadComment[] {
  if (!isUnread) return []
  const readAtMs = readAt ? Date.parse(readAt) : NaN
  return comments.filter(c => c.user?.id !== currentUserId && !arrivedBeforeRead(c.created_at, readAtMs))
}

// The newest message's id, mirroring Timeline's own lastMessageId memo (keep them
// in sync). The fully-read initial scroll top-aligns this rather than jumping to
// the document bottom.
export function lastMessageId(timeline: TimelineItem[]): string | null {
  for (let i = timeline.length - 1; i >= 0; i--) {
    const item = timeline[i]
    if (item.type === "message") return item.message.id
  }
  return null
}
