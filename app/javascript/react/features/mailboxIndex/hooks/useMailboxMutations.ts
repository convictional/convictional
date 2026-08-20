import { useCallback, useMemo } from "react"

import { apiFetch, errorMessage } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

import type { MailboxEntry } from "../types"

export interface MailboxMutations {
  archive: (id: string) => Promise<void>
  unarchive: (id: string) => Promise<void>
  markRead: (id: string) => Promise<void>
  markUnread: (id: string) => Promise<void>
  snooze: (id: string, snoozedUntil: string) => Promise<void>
  unsnooze: (id: string) => Promise<void>
}

// Store interface: each caller (inbox list, mailbox view) owns its own entry
// state and exposes the read/apply/rollback primitives below. Keeps mutation
// logic in one place without forcing one store to reach into another.
export interface MailboxEntryStore {
  findEntry: (id: string) => MailboxEntry | undefined
  applyOptimistic: (id: string, patch: Partial<MailboxEntry>) => MailboxEntry | undefined
  rollback: (previous: MailboxEntry) => void
}

export function useMailboxMutations(store: MailboxEntryStore): MailboxMutations {
  const { findEntry, applyOptimistic, rollback } = store

  const runMutation = useCallback(
    async (id: string, patch: Partial<MailboxEntry>, url: string, body: unknown, errorMsg: string): Promise<void> => {
      const previous = findEntry(id) ?? null
      applyOptimistic(id, patch)
      try {
        const init: RequestInit = { method: "POST" }
        if (body !== undefined) init.body = JSON.stringify(body)
        await apiFetch(url, init)
      } catch (e) {
        if (previous) rollback(previous)
        showFlash(errorMessage(e, errorMsg))
        throw e
      }
    },
    [findEntry, applyOptimistic, rollback]
  )

  return useMemo(
    () => ({
      archive: id =>
        runMutation(id, { is_archived: true }, `/api/mailbox_entries/${id}/archive`, undefined, "Couldn't archive."),
      unarchive: id =>
        runMutation(
          id,
          { is_archived: false, is_snoozed: false, snoozed_until: null },
          `/api/mailbox_entries/${id}/unarchive`,
          undefined,
          "Couldn't unarchive."
        ),
      markRead: id =>
        runMutation(
          id,
          { is_unread: false },
          `/api/mailbox_entries/${id}/mark_read`,
          undefined,
          "Couldn't mark read."
        ),
      markUnread: id =>
        runMutation(
          id,
          { is_unread: true },
          `/api/mailbox_entries/${id}/mark_unread`,
          undefined,
          "Couldn't mark unread."
        ),
      snooze: (id, snoozedUntil) =>
        runMutation(
          id,
          { is_archived: true, is_snoozed: true, snoozed_until: snoozedUntil },
          `/api/mailbox_entries/${id}/snooze`,
          { snoozed_until: snoozedUntil },
          "Couldn't snooze."
        ),
      unsnooze: id =>
        runMutation(
          id,
          { is_archived: false, is_snoozed: false, snoozed_until: null },
          `/api/mailbox_entries/${id}/unsnooze`,
          undefined,
          "Couldn't unsnooze."
        ),
    }),
    [runMutation]
  )
}
