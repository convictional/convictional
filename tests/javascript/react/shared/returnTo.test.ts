import { describe, expect, test } from "vitest"

import { withRedirectTo, withReturnTo } from "~/react/shared/returnTo"

describe("returnTo", () => {
  test("withReturnTo appends the content back-link contract (return_to)", () => {
    expect(withReturnTo("/login", "https://app.test/goals/123?tab=open")).toBe(
      "/login?return_to=%2Fgoals%2F123%3Ftab%3Dopen"
    )
  })

  test("withRedirectTo appends the post-auth contract (redirect_to)", () => {
    expect(withRedirectTo("/login", "https://app.test/goals/123")).toBe("/login?redirect_to=%2Fgoals%2F123")
  })

  test("preserves an existing query on the destination", () => {
    expect(withRedirectTo("/login?intent=signup", "https://app.test/mailbox")).toBe(
      "/login?intent=signup&redirect_to=%2Fmailbox"
    )
  })

  test("falls back to the href unchanged when the base URL is unusable", () => {
    expect(withRedirectTo("/login", "")).toBe("/login")
  })
})
