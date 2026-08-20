import { describe, expect, test } from "vitest"

import { emailThreadBackNavigation } from "~/react/features/emailThreadShow/urls"

describe("emailThreadBackNavigation", () => {
  test("defaults to the inbox when there is no return_to", () => {
    expect(emailThreadBackNavigation(undefined)).toEqual({ url: "/", label: "Back to inbox" })
  })

  test("labels a mailbox custom-view return_to", () => {
    expect(emailThreadBackNavigation("/?mailbox_view_id=abc")).toEqual({
      url: "/?mailbox_view_id=abc",
      label: "Back to custom view",
    })
  })

  test("derives a resource label from a safe return_to", () => {
    expect(emailThreadBackNavigation("/posts")).toEqual({ url: "/posts", label: "Back to posts" })
    expect(emailThreadBackNavigation("/search?q=hi")).toEqual({ url: "/search?q=hi", label: "Back to search" })
  })

  test("falls back to the inbox for an unsafe (off-site) return_to", () => {
    expect(emailThreadBackNavigation("https://evil.example.com")).toEqual({ url: "/", label: "Back to inbox" })
  })
})
