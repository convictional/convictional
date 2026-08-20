import { SnoozeDropdown } from "~/react/composites/MailboxActionBar/SnoozeDropdown"
import { Tooltip } from "~/react/ui/Tooltip"

import type { MailboxMutations } from "../hooks/useMailboxMutations"
import type { MailboxEntry } from "../types"

interface HoverActionBarProps {
  entry: MailboxEntry
  mutations: MailboxMutations
  onArchive: () => void
  onSnooze: (snoozedUntil: string) => Promise<void>
  snoozeOpen: boolean
  onSnoozeOpenChange: (open: boolean) => void
  timezone: string | null
}

// Self-contained hover action bar for inbox rows. Imports SnoozeDropdown only —
// the show-page MailboxActionBar is shaped for navigation after archive, which
// the inbox row does not want. See plan PR 3 §"HoverActionBar is self-contained".
export function HoverActionBar({
  entry,
  mutations,
  onArchive,
  onSnooze,
  snoozeOpen,
  onSnoozeOpenChange,
  timezone,
}: HoverActionBarProps) {
  // Snoozed entries are archived in the data model (snooze sets archived=true), but
  // unsnoozing already unarchives at the provider. Showing both "Unarchive" and
  // "Unsnooze" as separate affordances is confusing, so suppress the archive toggle
  // while snoozed and let Unsnooze own restoration.
  return (
    <div className="flex items-center gap-4">
      {entry.is_snoozed ? null : entry.is_archived ? (
        <Tooltip content="Unarchive">
          <button
            type="button"
            onClick={() => mutations.unarchive(entry.id)}
            aria-label="Unarchive"
            className="cursor-pointer"
            data-action="unarchive"
          >
            <span className="material-symbols-outlined text-xl text-base-600 hover:text-base-800">unarchive</span>
          </button>
        </Tooltip>
      ) : (
        <Tooltip content="Archive">
          <button
            type="button"
            onClick={onArchive}
            aria-label="Archive"
            className="cursor-pointer"
            data-action="archive"
          >
            <span className="material-symbols-outlined text-xl text-base-600 hover:text-base-800">archive</span>
          </button>
        </Tooltip>
      )}
      {entry.is_unread ? (
        <Tooltip content="Mark read">
          <button
            type="button"
            onClick={() => mutations.markRead(entry.id)}
            aria-label="Mark read"
            className="cursor-pointer"
            data-action="mark-read"
          >
            <span className="material-symbols-outlined text-xl text-base-600 hover:text-base-800">drafts</span>
          </button>
        </Tooltip>
      ) : (
        <Tooltip content="Mark unread">
          <button
            type="button"
            onClick={() => mutations.markUnread(entry.id)}
            aria-label="Mark unread"
            className="cursor-pointer"
            data-action="mark-unread"
          >
            <span className="material-symbols-outlined text-xl text-base-600 hover:text-base-800">
              mark_email_unread
            </span>
          </button>
        </Tooltip>
      )}
      {entry.is_snoozed ? (
        <Tooltip content="Unsnooze">
          <button
            type="button"
            onClick={() => mutations.unsnooze(entry.id)}
            aria-label="Unsnooze"
            className="cursor-pointer"
          >
            <span className="material-symbols-outlined text-xl text-base-600 hover:text-base-800">alarm_off</span>
          </button>
        </Tooltip>
      ) : (
        <SnoozeDropdown
          isOpen={snoozeOpen}
          onOpenChange={onSnoozeOpenChange}
          onSnooze={onSnooze}
          timezone={timezone}
          buttonClassName="cursor-pointer"
          withHotkey={false}
        />
      )}
    </div>
  )
}
