import { describe, expect, test } from "vitest"

import {
  OPTIMISTIC_GUARD_MS,
  localMutationWins,
} from "../../../../../app/javascript/react/features/mailboxIndex/optimisticMerge"
import { shouldShowEntry } from "../../../../../app/javascript/react/shared/queries/mailboxEntries"
import type {
  MailboxEntry,
  MailboxEntryListItem,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

const now = Date.parse("2026-05-01T00:00:00Z")

function makeEntry(overrides: Partial<MailboxEntry> = {}): MailboxEntry {
  return {
    id: "e1",
    resource_type: "Chat",
    href: "/chats/1",
    title: "Test",
    preview: null,
    sender_display: null,
    last_activity_at: "2026-05-01T00:00:00Z",
    is_unread: true,
    is_archived: false,
    is_snoozed: false,
    snoozed_until: null,
    is_assigned_to_me: false,
    is_shared: false,
    email: null,
    chat: {
      is_group_chat: false,
      is_dm: true,
      collaborator_count: 2,
      counterparty: null,
      last_message_author: null,
      member_avatars: [],
      overflow_count: 0,
      last_comment: null,
      last_comment_author_name: null,
    },
    post: null,
    goal: null,
    ...overrides,
  }
}

// Mirrors the module-private `preserveMutated` merge: adopt each incoming server
// item unless a recent local optimistic copy should win.
function mergeOnSync(
  incoming: MailboxEntryListItem[],
  previous: MailboxEntry[],
  nowMs: number
): MailboxEntry[] {
  const previousById = new Map(previous.map(entry => [entry.id, entry]))
  return incoming.map(item => {
    const local = previousById.get(item.id)
    return localMutationWins(local, nowMs) ? local : (item as MailboxEntry)
  })
}

describe("localMutationWins (recency window)", () => {
  // #9130 primary: a just-archived local copy wins over a concurrent server sync
  // that still shows it un-archived, because the stamp is inside the guard window
  // (regardless of the server's synced_at clock).
  test("keeps a recently-mutated local copy over a stale server sync", () => {
    const local = makeEntry({ is_archived: true, mutatedAt: now })
    const server = makeEntry({ is_archived: false })

    // Reference just after the stamp — still inside the 3s window.
    expect(localMutationWins(local, now + 50)).toBe(true)

    const [merged] = mergeOnSync([server], [local], now + 50)
    expect(merged.is_archived).toBe(true)
    expect(shouldShowEntry(merged, "inbox")).toBe(false)
  })

  // Bounded: once the stamp ages past the guard window, the local copy no longer
  // pins — the server copy is adopted, so there's no permanent stale state.
  test("adopts the server copy once the stamp ages past the guard window", () => {
    const local = makeEntry({ is_archived: true, mutatedAt: now - OPTIMISTIC_GUARD_MS - 1 })
    const server = makeEntry({ is_archived: false })

    expect(localMutationWins(local, now)).toBe(false)

    const [merged] = mergeOnSync([server], [local], now)
    expect(merged.is_archived).toBe(false)
    expect(shouldShowEntry(merged, "inbox")).toBe(true)
  })

  // No stamp: a never-mutated local entry never wins, whatever the reference.
  test("server wins when the local copy has no mutatedAt stamp", () => {
    const local = makeEntry({ mutatedAt: undefined })
    expect(localMutationWins(local, now)).toBe(false)
    expect(localMutationWins(local, 0)).toBe(false)
    expect(localMutationWins(undefined, now)).toBe(false)
  })
})
