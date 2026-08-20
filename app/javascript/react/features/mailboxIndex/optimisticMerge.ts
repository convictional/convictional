import type { MailboxEntry } from "./types"

export const OPTIMISTIC_GUARD_MS = 3000

// The mutatedAt-wins rule (load-bearing), shared by the inbox list
// (useMailboxEntries) and the view (useMailboxView). An entry carries a local
// `mutatedAt` (a browser-clock stamp) only while an optimistic mutation is in
// flight. `nowMs` is the browser clock at merge time: local wins while its
// stamp is recent. This is a same-clock recency window, deliberately not a
// cross-clock comparison against a server timestamp (which can go stale-wins).
export function localMutationWins(local: MailboxEntry | undefined, nowMs: number): local is MailboxEntry {
  return local?.mutatedAt !== undefined && nowMs - local.mutatedAt < OPTIMISTIC_GUARD_MS
}
