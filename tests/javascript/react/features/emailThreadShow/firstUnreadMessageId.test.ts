import { describe, expect, it } from "vitest"

import { firstUnreadMessageId } from "~/react/features/emailThreadShow/readState"
import type { TimelineItem } from "~/react/shared/types"

// `createdAt` lets a caller diverge the top-level `created_at` from the message's
// `received_at` to exercise the two-time-base read semantics. By default they match.
const message = (id: string, receivedAt: string, createdAt: string = receivedAt): TimelineItem => ({
  type: "message",
  item_id: id,
  created_at: createdAt,
  event: null,
  message: {
    id,
    message_type: "received",
    subject: null,
    raw_sender: null,
    sender_name: id,
    sender_email: `${id}@example.com`,
    to: [],
    cc: [],
    bcc: [],
    preview: null,
    received_at: receivedAt,
    sent_at: null,
    created_at: createdAt,
    external_thread_id: null,
    message_id: null,
    content_url: `/content/${id}`,
    reply_url: "",
    forward_url: "",
    view_original_url: "",
  },
})

const TIMELINE = [
  message("a", "2025-01-01T00:00:00Z"),
  message("b", "2025-01-02T00:00:00Z"),
  message("c", "2025-01-03T00:00:00Z"),
]

describe("firstUnreadMessageId", () => {
  it("returns null when the thread is fully read", () => {
    // All read (is_unread === false): no first-unread target — the caller falls
    // back to scrolling the document bottom rather than a specific message.
    expect(firstUnreadMessageId(TIMELINE, "2025-01-03T12:00:00Z", false)).toBeNull()
    expect(firstUnreadMessageId(TIMELINE, null, false)).toBeNull()
  })

  it("returns the first message on an untouched unread thread", () => {
    // Never read (read_at null, is_unread true): every message is unread, so the
    // oldest one is the target.
    expect(firstUnreadMessageId(TIMELINE, null, true)).toBe("a")
  })

  it("returns the oldest message that arrived at/after read_at", () => {
    // Read up to 2025-01-01T12:00 then went unread: "a" arrived before, "b" after.
    expect(firstUnreadMessageId(TIMELINE, "2025-01-01T12:00:00Z", true)).toBe("b")
  })

  it("targets the last message when it is the sole unread one (the racy case)", () => {
    // Only the final message arrived after read_at — the scenario that landed at
    // the document bottom or top nondeterministically with the old timer.
    expect(firstUnreadMessageId(TIMELINE, "2025-01-02T12:00:00Z", true)).toBe("c")
  })

  it("returns null when an unread thread has no message at/after read_at", () => {
    // Unread only because of a (non-message) comment: no unread email message, so
    // there is no first-unread message to target.
    expect(firstUnreadMessageId(TIMELINE, "2025-01-03T12:00:00Z", true)).toBeNull()
  })

  it("keys off received_at, not the top-level created_at", () => {
    // received_at is at/after read_at while created_at is before — the message
    // counts as unread because the read check uses received_at ?? created_at.
    const receivedLate = [message("a", "2025-01-05T00:00:00Z", "2025-01-01T00:00:00Z")]
    expect(firstUnreadMessageId(receivedLate, "2025-01-03T00:00:00Z", true)).toBe("a")

    // Converse: read by received_at even though created_at is newer → not unread.
    const receivedEarly = [message("a", "2025-01-01T00:00:00Z", "2025-01-05T00:00:00Z")]
    expect(firstUnreadMessageId(receivedEarly, "2025-01-03T00:00:00Z", true)).toBeNull()
  })
})
