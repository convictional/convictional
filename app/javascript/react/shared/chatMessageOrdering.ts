import type { ChatMessage } from "./types"

// Total order matching the server's list ordering: created_at ASC, then id ASC
// (see infra/db.py:1253-1257). created_at is an ISO-8601 string, so localeCompare
// is a correct lexical comparison for it.
export function compareMessages(a: ChatMessage, b: ChatMessage): number {
  const t = a.created_at.localeCompare(b.created_at)
  return t !== 0 ? t : a.id.localeCompare(b.id)
}

// Returns a NEW array with `msg` inserted in order. Dedupes by id (existing wins).
// Also reports whether the message landed anywhere other than the tail — i.e. an
// out-of-order arrival — so callers can log it.
export function insertInOrder(
  messages: ChatMessage[],
  msg: ChatMessage
): { messages: ChatMessage[]; inserted: boolean; outOfOrder: boolean } {
  if (messages.some(m => m.id === msg.id)) {
    return { messages, inserted: false, outOfOrder: false }
  }
  // Fast path: in-order arrival appends at the tail (the overwhelmingly common case,
  // identical to today's behavior).
  const tail = messages[messages.length - 1]
  if (!tail || compareMessages(tail, msg) <= 0) {
    return { messages: [...messages, msg], inserted: true, outOfOrder: false }
  }
  // Out-of-order: find the correct slot. Lists are small (a screenful) so a linear
  // scan is fine; switch to binary search only if profiling says so.
  const idx = messages.findIndex(m => compareMessages(m, msg) > 0)
  const at = idx === -1 ? messages.length : idx
  return { messages: [...messages.slice(0, at), msg, ...messages.slice(at)], inserted: true, outOfOrder: true }
}

// Merges a page of messages into `prev`, dropping any whose id is already
// present, and joins them on the requested side: "older" prepends (backward
// pagination), "newer" appends (forward pagination / catch-up). Does NOT sort —
// callers supply `incoming` already ordered, or sort the result themselves.
export function mergeDedup(prev: ChatMessage[], incoming: ChatMessage[], position: "older" | "newer"): ChatMessage[] {
  const existingIds = new Set(prev.map(m => m.id))
  const deduped = incoming.filter(m => !existingIds.has(m.id))
  return position === "older" ? [...deduped, ...prev] : [...prev, ...deduped]
}
