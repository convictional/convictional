import { useRef } from "react"

import { GoalBadge } from "~/react/composites/goals/GoalBadge"
import { isVisibleViewRow } from "~/react/shared/queries/mailboxViewEntries"
import { LoadMoreSentinel } from "~/react/ui/LoadMoreSentinel"
import { Tooltip } from "~/react/ui/Tooltip"

import { useHoverRecovery } from "../hooks/useHoverRecovery"
import type { MailboxMutations } from "../hooks/useMailboxMutations"
import type { MailboxEntry, ViewSection } from "../types"
import { EntryRow } from "./EntryRow"

interface MailboxViewSectionsProps {
  sections: ViewSection[]
  entriesById: Record<string, MailboxEntry>
  mutations: MailboxMutations
  selectedId: string | null
  onSelect: (id: string) => void
  onArchiveWithUndo: (entry: MailboxEntry) => void
  onSnoozeWithUndo: (entry: MailboxEntry, snoozedUntil: string) => Promise<void>
  snoozeOpenEntryId: string | null
  onSnoozeOpenChange: (entryId: string, open: boolean) => void
  timezone: string | null
  // A ranked sort is mechanically one untitled section rendered flat: no section header pill,
  // no GoalBadge, no per-section "Nothing in this category" wrapper.
  isRanked?: boolean
  // Cache-hit hydration is paginated; the sentinel at the end of the list hydrates the next page as
  // it scrolls into view. hasMore is false during live generation (entries stream in directly).
  hasMoreEntries?: boolean
  loadingMoreEntries?: boolean
  onLoadMoreEntries?: () => void
}

function EntryRows({
  entries,
  mutations,
  selectedId,
  onSelect,
  onArchiveWithUndo,
  onSnoozeWithUndo,
  snoozeOpenEntryId,
  onSnoozeOpenChange,
  timezone,
}: {
  entries: MailboxEntry[]
  mutations: MailboxMutations
  selectedId: string | null
  onSelect: (id: string) => void
  onArchiveWithUndo: (entry: MailboxEntry) => void
  onSnoozeWithUndo: (entry: MailboxEntry, snoozedUntil: string) => Promise<void>
  snoozeOpenEntryId: string | null
  onSnoozeOpenChange: (entryId: string, open: boolean) => void
  timezone: string | null
}) {
  const listRef = useRef<HTMLUListElement>(null)
  const forcedHoverId = useHoverRecovery(
    listRef,
    entries.map(entry => entry.id)
  )

  return (
    <ul className="mailbox-view-entries px-3.5" ref={listRef}>
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
  )
}

const visibleEntries = (section: ViewSection, entriesById: Record<string, MailboxEntry>): MailboxEntry[] =>
  section.mailbox_entry_ids.map(id => entriesById[id]).filter(isVisibleViewRow)

export function MailboxViewSections({
  sections,
  entriesById,
  mutations,
  selectedId,
  onSelect,
  onArchiveWithUndo,
  onSnoozeWithUndo,
  snoozeOpenEntryId,
  onSnoozeOpenChange,
  timezone,
  isRanked = false,
  hasMoreEntries = false,
  loadingMoreEntries = false,
  onLoadMoreEntries,
}: MailboxViewSectionsProps) {
  const rowProps = {
    mutations,
    selectedId,
    onSelect,
    onArchiveWithUndo,
    onSnoozeWithUndo,
    snoozeOpenEntryId,
    onSnoozeOpenChange,
    timezone,
  }

  const loadMoreSentinel = hasMoreEntries && onLoadMoreEntries && (
    <LoadMoreSentinel onIntersect={onLoadMoreEntries} loading={loadingMoreEntries} />
  )

  if (isRanked) {
    // One flat list — sections[0] holds the score-ordered ids (or nothing yet, mid-stream).
    return (
      <div id="view-sections">
        <EntryRows entries={sections[0] ? visibleEntries(sections[0], entriesById) : []} {...rowProps} />
        {loadMoreSentinel}
      </div>
    )
  }

  return (
    <div id="view-sections">
      {sections.map((section, sectionIndex) => {
        const entries = visibleEntries(section, entriesById)
        return (
          <div
            key={`${sectionIndex}-${section.title}`}
            id={`view-section-${sectionIndex}`}
            className="view-section"
            data-section-index={sectionIndex}
          >
            <div className="sticky top-16 z-20 pt-3 pb-2 bg-base-100">
              <div className="flex items-center gap-1.5">
                {section.goal ? (
                  <GoalBadge goal={section.goal} />
                ) : (
                  <>
                    <span className="inline-flex items-center bg-primary/10 rounded-full px-3 py-1 text-sm font-medium text-primary">
                      {section.title}
                    </span>
                    {section.description && (
                      <Tooltip content={section.description}>
                        <span className="material-symbols-outlined text-base text-base-content/40 cursor-help">
                          info
                        </span>
                      </Tooltip>
                    )}
                  </>
                )}
              </div>
            </div>
            {entries.length === 0 ? (
              <div className="p-4 text-center text-base-500 text-sm italic">Nothing in this category</div>
            ) : (
              <EntryRows entries={entries} {...rowProps} />
            )}
          </div>
        )
      })}
      {loadMoreSentinel}
    </div>
  )
}
