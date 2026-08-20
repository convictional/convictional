import { describe, expect, test } from "vitest"

import { isContinuation } from "../../../../app/javascript/react/shared/messageGrouping"
import type { ChatMessage } from "../../../../app/javascript/react/shared/types"

function makeMessage(overrides: Partial<ChatMessage> & { user?: Partial<ChatMessage["user"]> } = {}): ChatMessage {
  const { user: userOverrides, ...rest } = overrides
  return {
    id: "msg-1",
    content: "hello",
    created_at: "2026-04-16T12:00:00Z",
    edited_at: null,
    reactions: {},
    user: { id: "user-1", display_name: "Alice", picture: null, ...userOverrides },
    link_preview: null,
    reply_to: null,
    ...rest,
  } satisfies ChatMessage
}

describe("isContinuation", () => {
  test("returns false when there is no previous message", () => {
    expect(isContinuation(undefined, makeMessage())).toBe(false)
  })

  test("returns true for same user within 5 minutes", () => {
    const prev = makeMessage({ created_at: "2026-04-16T12:00:00Z" })
    const current = makeMessage({ id: "msg-2", created_at: "2026-04-16T12:03:00Z" })
    expect(isContinuation(prev, current)).toBe(true)
  })

  test("returns true for same user at exactly 5 minutes (boundary)", () => {
    const prev = makeMessage({ created_at: "2026-04-16T12:00:00Z" })
    const current = makeMessage({ id: "msg-2", created_at: "2026-04-16T12:05:00Z" })
    expect(isContinuation(prev, current)).toBe(true)
  })

  test("returns false for same user over 5 minutes", () => {
    const prev = makeMessage({ created_at: "2026-04-16T12:00:00Z" })
    const current = makeMessage({ id: "msg-2", created_at: "2026-04-16T12:05:01Z" })
    expect(isContinuation(prev, current)).toBe(false)
  })

  test("returns false for different user within 5 minutes", () => {
    const prev = makeMessage({ created_at: "2026-04-16T12:00:00Z" })
    const current = makeMessage({
      id: "msg-2",
      created_at: "2026-04-16T12:01:00Z",
      user: { id: "user-2", display_name: "Bob", picture: null },
    })
    expect(isContinuation(prev, current)).toBe(false)
  })

  test("returns true for messages with identical timestamps", () => {
    const prev = makeMessage({ created_at: "2026-04-16T12:00:00Z" })
    const current = makeMessage({ id: "msg-2", created_at: "2026-04-16T12:00:00Z" })
    expect(isContinuation(prev, current)).toBe(true)
  })

  test("groups a reply message from the same user within threshold", () => {
    const prev = makeMessage({ created_at: "2026-04-16T12:00:00Z" })
    const current = makeMessage({
      id: "msg-2",
      created_at: "2026-04-16T12:01:00Z",
      reply_to: { id: "other-msg", user_name: "Bob", content_preview: "hi", is_deleted: false },
    })
    expect(isContinuation(prev, current)).toBe(true)
  })

  test("returns false when messages arrive out of order (negative gap)", () => {
    const prev = makeMessage({ created_at: "2026-04-16T12:05:00Z" })
    const current = makeMessage({ id: "msg-2", created_at: "2026-04-16T12:00:00Z" })
    expect(isContinuation(prev, current)).toBe(false)
  })

  // Email thread comments reuse isContinuation but carry a nullable author, so
  // exercise that shape directly.
  test("groups same-author email comments within the window", () => {
    const prev = { user: { id: "user-1" }, created_at: "2026-04-16T12:00:00Z" }
    const current = { user: { id: "user-1" }, created_at: "2026-04-16T12:03:00Z" }
    expect(isContinuation(prev, current)).toBe(true)
  })

  test("returns false when either comment has a null author", () => {
    const withUser = { user: { id: "user-1" }, created_at: "2026-04-16T12:00:00Z" }
    const withoutUser = { user: null, created_at: "2026-04-16T12:01:00Z" }
    expect(isContinuation(withoutUser, withUser)).toBe(false)
    expect(isContinuation(withUser, withoutUser)).toBe(false)
  })
})
