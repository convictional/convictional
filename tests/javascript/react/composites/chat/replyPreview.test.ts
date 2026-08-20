import { describe, expect, test } from "vitest"

import { replyContentPreview } from "~/react/composites/chat/replyPreview"

describe("replyContentPreview", () => {
  test("strips markdown for short content", () => {
    expect(replyContentPreview("**hello** _world_ [link](http://x)")).toBe("hello world link")
  })

  test("truncates long content with an ellipsis", () => {
    const result = replyContentPreview("a".repeat(500))
    expect(result.endsWith("…")).toBe(true)
    expect(result.length).toBe(200)
  })

  test("returns empty string for empty input", () => {
    expect(replyContentPreview("")).toBe("")
  })
})
