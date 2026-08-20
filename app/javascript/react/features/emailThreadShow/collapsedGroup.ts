import { isContinuation } from "~/react/shared/messageGrouping"
import type { EmailThreadComment, TimelineItem } from "~/react/shared/types"

// One chronologically-sorted entry in a thread: either a timeline item (email
// message or activity event) or an internal comment. Comments carry an isGrouped
// flag set when they continue a same-author run (see mergeTimeline).
export type MergedEntry =
  | { kind: "timeline"; created_at: string; item: TimelineItem }
  | { kind: "comment"; created_at: string; comment: EmailThreadComment; isGrouped: boolean }

// Merge messages/events and comments into one chronological list, flagging
// consecutive same-author comments as grouped. Extracted from Timeline so the
// parent can reuse the exact ordering when deciding the collapsed group — a
// second, independent merge would risk disagreeing on tie-ordering.
export function mergeTimeline(items: TimelineItem[], comments: EmailThreadComment[]): MergedEntry[] {
  const timelineItems: MergedEntry[] = items.map(item => ({ kind: "timeline", created_at: item.created_at, item }))
  const commentItems: MergedEntry[] = comments.map(comment => ({
    kind: "comment",
    created_at: comment.created_at,
    comment,
    isGrouped: false,
  }))
  const sorted = [...timelineItems, ...commentItems].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  )
  // Flag each comment as grouped only when it follows another comment by the same
  // author within the window — a message/event in between resets the run. A reply
  // never collapses onto its predecessor: its quote block has to stay visible.
  for (let i = 0; i < sorted.length; i++) {
    const entry = sorted[i]
    if (entry.kind !== "comment") continue
    if (entry.comment.reply_to) continue
    const prev = sorted[i - 1]
    if (prev?.kind === "comment") {
      entry.isGrouped = isContinuation(prev.comment, entry.comment)
    }
  }
  return sorted
}

// True when this entry is the message or comment identified by id. Events are
// never a scroll/collapse boundary, so they never match.
export function entryMatchesId(entry: MergedEntry, id: string): boolean {
  if (entry.kind === "comment") return entry.comment.id === id
  if (entry.item.type === "message") return entry.item.message.id === id
  return false
}

// The compact "stack" that hides the run of read items before the first unread
// item behind a count bar, keeping the run's two ends visible as peeks
// (Gmail-style). Lets a long, mostly-read thread load with its subject in view
// instead of scrolled far down to the oldest unread message.
export interface CollapsedGroup {
  // How many merged entries the group spans — the caller renders
  // merged.slice(runLength) normally after it.
  runLength: number
  peekTop: MergedEntry
  peekBottom: MergedEntry
  hidden: MergedEntry[]
  hiddenEmailCount: number
  hiddenChatCount: number
}

// The stack only earns its keep when it hides at least this many entries — with
// fewer, the two peeks plus the bar would be as tall as just showing the previews.
const MIN_HIDDEN = 2

// Build the collapsed group for the read run before boundaryId (the first unread
// item), or null when there's no unread boundary or the run is too short to compact.
export function computeCollapsedGroup(merged: MergedEntry[], boundaryId: string | null): CollapsedGroup | null {
  if (!boundaryId) return null
  const boundaryIndex = merged.findIndex(entry => entryMatchesId(entry, boundaryId))
  if (boundaryIndex < 0) return null
  const run = merged.slice(0, boundaryIndex)
  if (run.length < MIN_HIDDEN + 2) return null
  const hidden = run.slice(1, run.length - 1)
  return {
    runLength: run.length,
    peekTop: run[0],
    peekBottom: run[run.length - 1],
    hidden,
    hiddenEmailCount: hidden.filter(e => e.kind === "timeline" && e.item.type === "message").length,
    hiddenChatCount: hidden.filter(e => e.kind === "comment").length,
  }
}
