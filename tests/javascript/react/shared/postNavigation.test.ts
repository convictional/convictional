import { describe, expect, it } from "vitest"

import { postBackNavigation, postNavigationSearch } from "~/react/shared/postNavigation"

describe("postBackNavigation", () => {
  it("labels the posts index specifically", () => {
    expect(postBackNavigation("/posts", undefined)).toEqual({ url: "/posts", label: "Back to posts" })
    expect(postBackNavigation("/posts?group_id=g1", undefined)).toEqual({
      url: "/posts?group_id=g1",
      label: "Back to posts",
    })
  })

  it("labels any other return_to target generically", () => {
    expect(postBackNavigation("/posts/other", undefined)).toEqual({ url: "/posts/other", label: "Back" })
  })

  it("falls back to the inbox when opened from a mailbox entry", () => {
    expect(postBackNavigation(undefined, "entry-1")).toEqual({ url: "/", label: "Back to inbox" })
  })

  it("falls back to the posts index otherwise", () => {
    expect(postBackNavigation(undefined, undefined)).toEqual({ url: "/posts", label: "Back to posts" })
  })

  it("ignores an unsafe return_to and uses the fallback", () => {
    expect(postBackNavigation("//evil.com", undefined)).toEqual({ url: "/posts", label: "Back to posts" })
  })
})

describe("postNavigationSearch", () => {
  it("includes only the params that are present", () => {
    expect(postNavigationSearch("/posts", "entry-1")).toEqual({ return_to: "/posts", mailbox_entry_id: "entry-1" })
    expect(postNavigationSearch("/posts", undefined)).toEqual({ return_to: "/posts" })
    expect(postNavigationSearch(undefined, "entry-1")).toEqual({ mailbox_entry_id: "entry-1" })
    expect(postNavigationSearch(undefined, undefined)).toEqual({})
  })

  it("drops an unsafe return_to but keeps the mailbox entry", () => {
    expect(postNavigationSearch("//evil.com", "entry-1")).toEqual({ mailbox_entry_id: "entry-1" })
  })
})
