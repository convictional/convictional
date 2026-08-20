import { describe, expect, it } from "vitest"

import { unreadComments } from "~/react/features/emailThreadShow/readState"
import type { EmailThreadComment } from "~/react/shared/types"

const comment = (id: string, createdAt: string, userId: string): EmailThreadComment => ({
  id,
  global_id: `gid://convictional/EmailThreadComment/${id}`,
  content: id,
  user: { id: userId, display_name: userId, picture: null },
  created_at: createdAt,
  updated_at: createdAt,
  reactions: {},
  link_preview: null,
  attachments: [],
  reply_to: null,
})

const VIEWER = "viewer"
const OTHER = "other"

const COMMENTS = [
  comment("a", "2025-01-01T00:00:00Z", OTHER),
  comment("b", "2025-01-02T00:00:00Z", OTHER),
  comment("c", "2025-01-03T00:00:00Z", OTHER),
]

const ids = (comments: EmailThreadComment[]) => comments.map(c => c.id)

describe("unreadComments", () => {
  it("returns nothing when the thread is fully read", () => {
    // The is_unread gate short-circuits regardless of timestamps.
    expect(unreadComments(COMMENTS, "2024-01-01T00:00:00Z", false, VIEWER)).toEqual([])
    expect(unreadComments(COMMENTS, null, false, VIEWER)).toEqual([])
  })

  it("returns every comment on an untouched unread thread", () => {
    // Never read (read_at null, is_unread true): all comments count as unread.
    expect(ids(unreadComments(COMMENTS, null, true, VIEWER))).toEqual(["a", "b", "c"])
  })

  it("returns comments created at/after read_at in display order", () => {
    // Read up to 2025-01-01T12:00 then went unread: "a" is before, "b"/"c" after.
    expect(ids(unreadComments(COMMENTS, "2025-01-01T12:00:00Z", true, VIEWER))).toEqual(["b", "c"])
  })

  it("excludes the viewer's own comments", () => {
    // A comment you authored never counts toward the divider, even when unread —
    // otherwise posting a comment would raise a "1 new comment" divider above it.
    const mixed = [
      comment("a", "2025-01-02T00:00:00Z", OTHER),
      comment("b", "2025-01-03T00:00:00Z", VIEWER),
      comment("c", "2025-01-04T00:00:00Z", OTHER),
    ]
    expect(ids(unreadComments(mixed, null, true, VIEWER))).toEqual(["a", "c"])
  })

  it("counts comments with a null author (excludable only by timestamp)", () => {
    // A system/authorless comment has no user id, so it never matches the viewer
    // and is included when unread.
    const authorless = [{ ...comment("a", "2025-01-02T00:00:00Z", OTHER), user: null }]
    expect(ids(unreadComments(authorless, null, true, VIEWER))).toEqual(["a"])
  })
})
