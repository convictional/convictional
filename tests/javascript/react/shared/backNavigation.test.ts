import { describe, expect, test } from "vitest"

import { backNavigation } from "~/react/shared/backNavigation"

const FALLBACK = { url: "/chats", label: "Back to chats" }

describe("backNavigation", () => {
  test("returns the caller's fallback when return_to is absent", () => {
    expect(backNavigation(undefined, FALLBACK)).toEqual(FALLBACK)
  })

  test("labels each resource origin from its path prefix, preserving the query", () => {
    expect(backNavigation("/documents", FALLBACK)).toEqual({ url: "/documents", label: "Back to documents" })
    expect(backNavigation("/documents?filter=mine", FALLBACK)).toEqual({
      url: "/documents?filter=mine",
      label: "Back to documents",
    })
    // Nested under a resource index (a sibling document) still labels to the index,
    // matching the server's route-path prefix match.
    expect(backNavigation("/documents/abc", FALLBACK)).toEqual({ url: "/documents/abc", label: "Back to documents" })
    expect(backNavigation("/posts", FALLBACK).label).toBe("Back to posts")
    expect(backNavigation("/goals", FALLBACK).label).toBe("Back to goals")
    expect(backNavigation("/meetings", FALLBACK).label).toBe("Back to meetings")
    expect(backNavigation("/search?q=x", FALLBACK).label).toBe("Back to search")
  })

  test("labels the inbox root, and its saved/template views as a custom view", () => {
    expect(backNavigation("/", FALLBACK)).toEqual({ url: "/", label: "Back to inbox" })
    expect(backNavigation("/?sort=oldest", FALLBACK)).toEqual({ url: "/?sort=oldest", label: "Back to inbox" })
    expect(backNavigation("/?mailbox_view_id=abc", FALLBACK).label).toBe("Back to custom view")
    expect(backNavigation("/?mailbox_view_template=getting_started", FALLBACK).label).toBe("Back to custom view")
  })

  test("labels an unknown same-origin path with a generic 'Back'", () => {
    expect(backNavigation("/whatever", FALLBACK)).toEqual({ url: "/whatever", label: "Back" })
  })

  test("drops an off-site return_to (no open redirect) and returns the fallback", () => {
    expect(backNavigation("//evil.com/phish", FALLBACK)).toEqual(FALLBACK)
    expect(backNavigation("https://evil.com/phish", FALLBACK)).toEqual(FALLBACK)
  })
})
