import { describe, expect, test } from "vitest"

import { computeWhatsNew } from "~/react/features/postShow/whatsNew"
import type { Decision, PostComment } from "~/react/shared/types"

import { buildComment, buildUser } from "./fixtures"

const LAST_VISIT = "2026-05-10T00:00:00Z"
const BEFORE = "2026-05-09T00:00:00Z"
const AFTER = "2026-05-11T00:00:00Z"
const VIEWER = "viewer-1"
const NO_DECISIONS: Decision[] = []
const NO_COMMENTS = new Map<string, PostComment>()

function buildDecision(overrides: Partial<Decision> = {}): Decision {
  return {
    id: "decision-1",
    comment_gid: "gid://convictional/PostComment/d1",
    comment_preview: null,
    decided_by: buildUser({ id: "decider" }),
    decided_at: AFTER,
    ...overrides,
  }
}

describe("computeWhatsNew", () => {
  test("returns null when there is no prior visit", () => {
    expect(computeWhatsNew([], NO_DECISIONS, NO_COMMENTS, null, VIEWER)).toBeNull()
  })

  test("returns null when nothing is new", () => {
    const comments = [buildComment({ id: "c1", created_at: BEFORE, user: buildUser({ id: "other" }) })]
    expect(computeWhatsNew(comments, NO_DECISIONS, NO_COMMENTS, LAST_VISIT, VIEWER)).toBeNull()
  })

  test("counts new top-level comments and excludes the viewer's own", () => {
    const comments = [
      buildComment({ id: "c1", created_at: AFTER, user: buildUser({ id: "other", display_name: "Bob" }) }),
      buildComment({ id: "c2", created_at: AFTER, user: buildUser({ id: VIEWER }) }),
      buildComment({ id: "c3", created_at: BEFORE, user: buildUser({ id: "other" }) }),
    ]
    const result = computeWhatsNew(comments, NO_DECISIONS, NO_COMMENTS, LAST_VISIT, VIEWER)
    expect(result).not.toBeNull()
    expect(result!.totalCount).toBe(1)
    expect(result!.firstNewCommentId).toBe("c1")
    expect(result!.groups).toHaveLength(1)
    expect(result!.groups[0].parentCommentId).toBeNull()
    expect(result!.groups[0].comments.map(c => c.id)).toEqual(["c1"])
  })

  test("groups new replies under their parent with the parent author name", () => {
    const parent = buildComment({
      id: "p1",
      created_at: BEFORE,
      user: buildUser({ id: "alice", display_name: "Alice" }),
      replies: [
        buildComment({ id: "r1", parent_id: "p1", created_at: AFTER, user: buildUser({ id: "bob" }) }),
        buildComment({ id: "r2", parent_id: "p1", created_at: BEFORE, user: buildUser({ id: "bob" }) }),
      ],
    })
    const result = computeWhatsNew([parent], NO_DECISIONS, NO_COMMENTS, LAST_VISIT, VIEWER)
    expect(result!.totalCount).toBe(1)
    const replyGroup = result!.groups.find(g => g.parentCommentId === "p1")
    expect(replyGroup).toBeDefined()
    expect(replyGroup!.contextAuthorName).toBe("Alice")
    expect(replyGroup!.comments.map(c => c.id)).toEqual(["r1"])
  })

  test("lists every new decision and counts each toward the total", () => {
    const c1 = buildComment({ id: "d1", created_at: BEFORE, user: buildUser({ id: "alice", display_name: "Alice" }) })
    const c2 = buildComment({ id: "d2", created_at: BEFORE, user: buildUser({ id: "bob", display_name: "Bob" }) })
    const newComment = buildComment({ id: "c1", created_at: AFTER, user: buildUser({ id: "carol" }) })
    const commentsByGid = new Map([
      ["gid-1", c1],
      ["gid-2", c2],
    ])
    const decisions = [
      buildDecision({ comment_gid: "gid-1", decided_at: AFTER, decided_by: buildUser({ id: "x", display_name: "Dee" }) }),
      buildDecision({ comment_gid: "gid-2", decided_at: AFTER, decided_by: buildUser({ id: "y", display_name: "Pat" }) }),
    ]

    const result = computeWhatsNew([newComment], decisions, commentsByGid, LAST_VISIT, VIEWER)
    // 1 new comment + 2 new decisions.
    expect(result!.totalCount).toBe(3)
    expect(result!.decisions.map(d => d.comment.id)).toEqual(["d1", "d2"])
    expect(result!.decisions[0].decidedByName).toBe("Dee")
  })

  test("seeds firstNewCommentId from the first new decision when there are no new comments", () => {
    const c1 = buildComment({ id: "d1", created_at: BEFORE, user: buildUser({ id: "alice" }) })
    const commentsByGid = new Map([["gid-1", c1]])
    const decisions = [buildDecision({ comment_gid: "gid-1", decided_at: AFTER, decided_by: buildUser({ id: "x" }) })]

    const result = computeWhatsNew([], decisions, commentsByGid, LAST_VISIT, VIEWER)
    expect(result!.firstNewCommentId).toBe("d1")
  })

  test("excludes the viewer's own decisions, pre-visit ones, and unresolvable comments", () => {
    const c1 = buildComment({ id: "d1", created_at: BEFORE, user: buildUser({ id: "alice" }) })
    const commentsByGid = new Map([["gid-1", c1]])
    const decisions = [
      buildDecision({ comment_gid: "gid-1", decided_at: AFTER, decided_by: buildUser({ id: VIEWER }) }), // own
      buildDecision({ comment_gid: "gid-1", decided_at: BEFORE, decided_by: buildUser({ id: "x" }) }), // pre-visit
      buildDecision({ comment_gid: "gid-missing", decided_at: AFTER, decided_by: buildUser({ id: "y" }) }), // unresolvable
    ]
    expect(computeWhatsNew([], decisions, commentsByGid, LAST_VISIT, VIEWER)).toBeNull()
  })
})
