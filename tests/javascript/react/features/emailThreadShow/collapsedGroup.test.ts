import { describe, expect, it } from "vitest"

import { computeCollapsedGroup, entryMatchesId, mergeTimeline } from "~/react/features/emailThreadShow/collapsedGroup"
import type { EmailThreadComment, TimelineItem } from "~/react/shared/types"

const message = (id: string, createdAt: string): TimelineItem => ({
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
    preview: `preview ${id}`,
    received_at: createdAt,
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

const comment = (id: string, createdAt: string): EmailThreadComment => ({
  id,
  global_id: `gid://convictional/EmailThreadComment/${id}`,
  content: `comment ${id}`,
  user: { id: `user-${id}` } as EmailThreadComment["user"],
  created_at: createdAt,
  updated_at: createdAt,
  reactions: {},
  link_preview: null,
  attachments: [],
  reply_to: null,
})

describe("mergeTimeline", () => {
  it("interleaves messages and comments in chronological order", () => {
    const merged = mergeTimeline(
      [message("a", "2025-01-01T00:00:00Z"), message("c", "2025-01-03T00:00:00Z")],
      [comment("b", "2025-01-02T00:00:00Z")]
    )
    expect(merged.map(e => (e.kind === "comment" ? e.comment.id : e.item.item_id))).toEqual(["a", "b", "c"])
  })
})

describe("computeCollapsedGroup", () => {
  const many = [
    message("a", "2025-01-01T00:00:00Z"),
    message("b", "2025-01-02T00:00:00Z"),
    message("c", "2025-01-03T00:00:00Z"),
    message("d", "2025-01-04T00:00:00Z"),
    message("e", "2025-01-05T00:00:00Z"),
  ]

  it("peeks the run's ends and hides the middle before the boundary", () => {
    // Boundary "e" (oldest unread): the read run a–d compacts with a & d peeked
    // and b, c hidden behind the bar.
    const group = computeCollapsedGroup(mergeTimeline(many, []), "e")
    expect(group).not.toBeNull()
    expect(group!.runLength).toBe(4)
    expect(entryMatchesId(group!.peekTop, "a")).toBe(true)
    expect(entryMatchesId(group!.peekBottom, "d")).toBe(true)
    expect(group!.hidden.map(e => (e.kind === "timeline" && e.item.type === "message" ? e.item.message.id : null))).toEqual([
      "b",
      "c",
    ])
    expect(group!.hiddenEmailCount).toBe(2)
    expect(group!.hiddenChatCount).toBe(0)
  })

  it("counts hidden comments as chats", () => {
    const group = computeCollapsedGroup(
      mergeTimeline(many, [comment("x", "2025-01-02T12:00:00Z"), comment("y", "2025-01-03T12:00:00Z")]),
      "e"
    )
    // Read run is a, b, x, c, y, d; peeks a & d; hidden b, x, c, y.
    expect(group!.hiddenEmailCount).toBe(2)
    expect(group!.hiddenChatCount).toBe(2)
  })

  it("compacts the read run when the boundary is a comment id", () => {
    // The first unread item can be a comment (commentScrollTargetId feeds the boundary),
    // not just a message — the run before it still compacts via entryMatchesId on the comment.
    const merged = mergeTimeline(many, [comment("z", "2025-01-06T00:00:00Z")])
    const group = computeCollapsedGroup(merged, "z")
    expect(group).not.toBeNull()
    // a–e all precede comment z, so the whole message run is the compacted run.
    expect(group!.runLength).toBe(5)
    expect(entryMatchesId(group!.peekTop, "a")).toBe(true)
    expect(entryMatchesId(group!.peekBottom, "e")).toBe(true)
    expect(group!.hiddenChatCount).toBe(0)
  })

  it("returns null when the read run is too short to compact", () => {
    // Only a, b read before boundary "c" — 2 items can't spare a hidden middle.
    expect(computeCollapsedGroup(mergeTimeline(many, []), "c")).toBeNull()
  })

  it("returns null with no boundary (fully-read thread)", () => {
    expect(computeCollapsedGroup(mergeTimeline(many, []), null)).toBeNull()
  })

  it("returns null when the boundary is the first item (nothing read before it)", () => {
    expect(computeCollapsedGroup(mergeTimeline(many, []), "a")).toBeNull()
  })
})
