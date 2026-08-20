import { describe, expect, it } from "vitest"

import { postShowUrl } from "~/react/features/postShow/urls"

describe("postShowUrl", () => {
  it("forwards mailbox_entry_id so the API resolves the entry", () => {
    expect(postShowUrl("post-1", "abc-123")).toBe("/api/posts/post-1?mailbox_entry_id=abc-123")
  })

  it("omits the param when there is no mailbox_entry_id", () => {
    expect(postShowUrl("post-1", undefined)).toBe("/api/posts/post-1")
    expect(postShowUrl("post-1")).toBe("/api/posts/post-1")
  })

  it("encodes the entry id", () => {
    expect(postShowUrl("post-1", "a/b c")).toBe("/api/posts/post-1?mailbox_entry_id=a%2Fb%20c")
  })
})
