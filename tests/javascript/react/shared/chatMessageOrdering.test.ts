import { describe, expect, test } from "vitest"

import { compareMessages, insertInOrder, mergeDedup } from "../../../../app/javascript/react/shared/chatMessageOrdering"
import type { ChatMessage } from "../../../../app/javascript/react/shared/types"

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "msg-1",
    content: "hello",
    created_at: "2026-04-16T12:00:00Z",
    edited_at: null,
    reactions: {},
    user: { id: "user-1", display_name: "Alice", picture: null },
    link_preview: null,
    reply_to: null,
    ...overrides,
  } as ChatMessage
}

describe("compareMessages", () => {
  test("orders by created_at ascending", () => {
    const earlier = makeMessage({ id: "a", created_at: "2026-04-16T12:00:00Z" })
    const later = makeMessage({ id: "b", created_at: "2026-04-16T12:00:01Z" })
    expect(compareMessages(earlier, later)).toBeLessThan(0)
    expect(compareMessages(later, earlier)).toBeGreaterThan(0)
  })

  test("falls back to id when created_at is equal", () => {
    const a = makeMessage({ id: "a", created_at: "2026-04-16T12:00:00Z" })
    const b = makeMessage({ id: "b", created_at: "2026-04-16T12:00:00Z" })
    expect(compareMessages(a, b)).toBeLessThan(0)
    expect(compareMessages(b, a)).toBeGreaterThan(0)
    expect(compareMessages(a, a)).toBe(0)
  })
})

describe("insertInOrder", () => {
  test("appends an in-order arrival at the tail and flags it in-order", () => {
    const existing = [
      makeMessage({ id: "a", created_at: "2026-04-16T12:00:00Z" }),
      makeMessage({ id: "b", created_at: "2026-04-16T12:00:01Z" }),
    ]
    const msg = makeMessage({ id: "c", created_at: "2026-04-16T12:00:02Z" })
    const { messages, inserted, outOfOrder } = insertInOrder(existing, msg)
    expect(messages.map(m => m.id)).toEqual(["a", "b", "c"])
    expect(inserted).toBe(true)
    expect(outOfOrder).toBe(false)
  })

  test("inserts an out-of-order arrival into the middle and flags it out-of-order", () => {
    const existing = [
      makeMessage({ id: "a", created_at: "2026-04-16T12:00:00Z" }),
      makeMessage({ id: "c", created_at: "2026-04-16T12:00:02Z" }),
    ]
    const msg = makeMessage({ id: "b", created_at: "2026-04-16T12:00:01Z" })
    const { messages, inserted, outOfOrder } = insertInOrder(existing, msg)
    expect(messages.map(m => m.id)).toEqual(["a", "b", "c"])
    expect(inserted).toBe(true)
    expect(outOfOrder).toBe(true)
  })

  test("is a no-op for a duplicate id", () => {
    const existing = [makeMessage({ id: "a", created_at: "2026-04-16T12:00:00Z" })]
    const { messages, inserted, outOfOrder } = insertInOrder(existing, makeMessage({ id: "a" }))
    expect(messages).toBe(existing)
    expect(inserted).toBe(false)
    expect(outOfOrder).toBe(false)
  })

  test("inserts into an empty list as an in-order tail append", () => {
    const msg = makeMessage({ id: "a" })
    const { messages, inserted, outOfOrder } = insertInOrder([], msg)
    expect(messages.map(m => m.id)).toEqual(["a"])
    expect(inserted).toBe(true)
    expect(outOfOrder).toBe(false)
  })

  test("uses the id tiebreaker for equal created_at without flapping", () => {
    const existing = [makeMessage({ id: "b", created_at: "2026-04-16T12:00:00Z" })]
    const msg = makeMessage({ id: "a", created_at: "2026-04-16T12:00:00Z" })
    const { messages, outOfOrder } = insertInOrder(existing, msg)
    // "a" sorts before "b" at the same timestamp, so it backfills (out of order).
    expect(messages.map(m => m.id)).toEqual(["a", "b"])
    expect(outOfOrder).toBe(true)
  })

  test("does not mutate the input array", () => {
    const existing = [makeMessage({ id: "c", created_at: "2026-04-16T12:00:02Z" })]
    insertInOrder(existing, makeMessage({ id: "b", created_at: "2026-04-16T12:00:01Z" }))
    expect(existing.map(m => m.id)).toEqual(["c"])
  })
})

describe("mergeDedup", () => {
  test("prepends older messages, dropping ids already present", () => {
    const prev = [makeMessage({ id: "c" }), makeMessage({ id: "d" })]
    const incoming = [makeMessage({ id: "a" }), makeMessage({ id: "b" }), makeMessage({ id: "c" })]
    const merged = mergeDedup(prev, incoming, "older")
    expect(merged.map(m => m.id)).toEqual(["a", "b", "c", "d"])
  })

  test("appends newer messages, dropping ids already present", () => {
    const prev = [makeMessage({ id: "a" }), makeMessage({ id: "b" })]
    const incoming = [makeMessage({ id: "b" }), makeMessage({ id: "c" }), makeMessage({ id: "d" })]
    const merged = mergeDedup(prev, incoming, "newer")
    expect(merged.map(m => m.id)).toEqual(["a", "b", "c", "d"])
  })

  test("preserves incoming order without sorting", () => {
    const prev = [makeMessage({ id: "a", created_at: "2026-04-16T12:00:00Z" })]
    const incoming = [
      makeMessage({ id: "z", created_at: "2026-04-16T12:00:09Z" }),
      makeMessage({ id: "m", created_at: "2026-04-16T12:00:05Z" }),
    ]
    expect(mergeDedup(prev, incoming, "newer").map(m => m.id)).toEqual(["a", "z", "m"])
  })

  test("returns all of prev unchanged when every incoming id is a duplicate", () => {
    const prev = [makeMessage({ id: "a" }), makeMessage({ id: "b" })]
    const merged = mergeDedup(prev, [makeMessage({ id: "a" })], "newer")
    expect(merged.map(m => m.id)).toEqual(["a", "b"])
  })

  test("does not mutate the input arrays", () => {
    const prev = [makeMessage({ id: "a" })]
    const incoming = [makeMessage({ id: "b" })]
    mergeDedup(prev, incoming, "older")
    expect(prev.map(m => m.id)).toEqual(["a"])
    expect(incoming.map(m => m.id)).toEqual(["b"])
  })
})
