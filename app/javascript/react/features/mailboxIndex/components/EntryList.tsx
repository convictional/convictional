import { useEffect, useRef } from "react"

import { EmptyState } from "~/react/ui/EmptyState"
import { LoadMoreSentinel } from "~/react/ui/LoadMoreSentinel"

import { useHoverRecovery } from "../hooks/useHoverRecovery"
import type { MailboxMutations } from "../hooks/useMailboxMutations"
import type { MailboxEntry, MailboxView } from "../types"
import { EntryListSkeleton } from "./EntryListSkeleton"
import { EntryRow } from "./EntryRow"
import { GoalsSpotlight } from "./GoalsSpotlight"

interface EntryListProps {
  entries: MailboxEntry[]
  view: MailboxView
  selectedId: string | null
  hasMore: boolean
  hasLoadedMore: boolean
  loading: boolean
  loadingMore: boolean
  onLoadMore: () => void
  onReturnToTop: () => void
  onSelect: (id: string) => void
  mutations: MailboxMutations
  onArchiveWithUndo: (entry: MailboxEntry) => void
  onSnoozeWithUndo: (entry: MailboxEntry, snoozedUntil: string) => Promise<void>
  snoozeOpenEntryId: string | null
  onSnoozeOpenChange: (entryId: string, open: boolean) => void
  timezone: string | null
}

const EMPTY_COPY: Record<MailboxView, { title: string; text: string }> = {
  inbox: { title: "Inbox zero", text: "You've cleared your inbox." },
  unread: { title: "All caught up", text: "You have no unread threads." },
  archived: { title: "No archived threads", text: "Archived threads will appear here." },
  sent: { title: "Nothing sent", text: "Sent emails will appear here." },
  drafts: { title: "No drafts", text: "Email drafts will appear here." },
  assigned_to_me: { title: "Nothing assigned", text: "Threads assigned to you will appear here." },
  snoozed: { title: "Nothing snoozed", text: "Snoozed threads will appear here." },
}

export function EntryList({
  entries,
  view,
  selectedId,
  hasMore,
  hasLoadedMore,
  loading,
  loadingMore,
  onLoadMore,
  onReturnToTop,
  onSelect,
  mutations,
  onArchiveWithUndo,
  onSnoozeWithUndo,
  snoozeOpenEntryId,
  onSnoozeOpenChange,
  timezone,
}: EntryListProps) {
  const liveRef = useRef<HTMLDivElement>(null)
  const forcedHoverId = useHoverRecovery(
    liveRef,
    entries.map(entry => entry.id)
  )

  // Reconcile the frozen, now-stale tail (pages 2+) on a genuine RETURN to the top:
  // the top marker must have scrolled out of view — the user browsed down into the
  // frozen pages — and then come back. Firing on mere visibility loops when the whole
  // list fits on screen (low per_page / tall viewport): the top marker never leaves,
  // so resetToFirstPage's collapse to page 1 is instantly refilled by the bottom
  // LoadMoreSentinel and reconciled again, forever. Requiring an intervening exit
  // breaks that cycle, and means a pure downward scroll never reconciles — only a
  // return up does.
  const topRef = useRef<HTMLDivElement>(null)
  const hasLeftTopRef = useRef(false)
  const onReturnToTopRef = useRef(onReturnToTop)
  onReturnToTopRef.current = onReturnToTop
  useEffect(() => {
    const el = topRef.current
    if (!el || !hasLoadedMore) return
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) {
        hasLeftTopRef.current = true
      } else if (hasLeftTopRef.current) {
        hasLeftTopRef.current = false
        onReturnToTopRef.current()
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasLoadedMore])

  if (loading && entries.length === 0) {
    return <EntryListSkeleton />
  }

  if (entries.length === 0) {
    const copy = EMPTY_COPY[view]
    return (
      <EmptyState title={copy.title} text={copy.text}>
        {view === "inbox" && (
          <div className="flex justify-center">
            <GoalsSpotlight />
          </div>
        )}
      </EmptyState>
    )
  }

  return (
    <div id="mailbox-entries-live" ref={liveRef}>
      <div ref={topRef} aria-hidden="true" className="h-px" />
      <ul className="mailbox-entries-page">
        {entries.map(entry => (
          <EntryRow
            key={entry.id}
            entry={entry}
            isSelected={entry.id === selectedId}
            mutations={mutations}
            onClick={() => onSelect(entry.id)}
            onArchive={() => onArchiveWithUndo(entry)}
            onSnooze={snoozedUntil => onSnoozeWithUndo(entry, snoozedUntil)}
            snoozeOpen={snoozeOpenEntryId === entry.id}
            onSnoozeOpenChange={open => onSnoozeOpenChange(entry.id, open)}
            timezone={timezone}
            forceHover={forcedHoverId === entry.id}
          />
        ))}
      </ul>
      {hasMore && <LoadMoreSentinel onIntersect={onLoadMore} loading={loadingMore} />}
    </div>
  )
}
