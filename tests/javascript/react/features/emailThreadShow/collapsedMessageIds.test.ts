import { describe, expect, it } from "vitest"

import { collapsedMessageIdsFor } from "~/react/features/emailThreadShow/readState"
import type { TimelineItem } from "~/react/shared/types"

const message = (id: string, receivedAt: string): TimelineItem => ({
  type: "message",
  item_id: id,
  created_at: receivedAt,
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
    created_at: receivedAt,
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

describe("collapsedMessageIdsFor", () => {
  it("collapses every read message except the most recent", () => {
    // A read thread (is_unread === false) collapses all but the last message even
    // when read_at is null — the seeded-but-read case that read_at alone missed.
    expect(collapsedMessageIdsFor(TIMELINE, null, false)).toEqual(new Set(["a", "b"]))
  })

  it("expands everything on an untouched unread thread", () => {
    expect(collapsedMessageIdsFor(TIMELINE, null, true)).toEqual(new Set())
  })

  it("collapses only messages that arrived before read_at on a partially-read thread", () => {
    // Thread went unread again after a new message arrived: messages before the
    // prior read time stay collapsed, the newly-arrived one expands.
    expect(collapsedMessageIdsFor(TIMELINE, "2025-01-01T12:00:00Z", true)).toEqual(new Set(["a"]))
  })
})
