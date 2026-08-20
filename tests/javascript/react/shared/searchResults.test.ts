import { describe, expect, test } from "vitest"

import { formatAuthor, resultNavigationUrl, type SearchResult } from "~/react/shared/searchResults"

function fakeResult(overrides: Partial<SearchResult>): SearchResult {
  return {
    id: "c1",
    title: "Title",
    author: null,
    content_type: "post",
    category: "activity",
    source_url: "/posts/abc",
    preview_content: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    relevance_score: null,
    metadata: {},
    shared_with_me: false,
    ...overrides,
  }
}

describe("formatAuthor", () => {
  test("returns single author unchanged", () => {
    expect(formatAuthor("Maren Kovacs")).toBe("Maren Kovacs")
  })

  test("returns two authors unchanged", () => {
    expect(formatAuthor("Leo Park, Maren Kovacs")).toBe("Leo Park, Maren Kovacs")
  })

  test("truncates three or more authors", () => {
    expect(formatAuthor("Leo Park, Maren Kovacs, Priya Chandrasekaran")).toBe(
      "Leo Park, Maren Kovacs, and 1 other"
    )
  })

  test("truncates five authors", () => {
    expect(formatAuthor("Maren Kovacs, Darren Okafor, Priya Chandrasekaran, Tessa Nguyen, Leo Park")).toBe(
      "Maren Kovacs, Darren Okafor, and 3 others"
    )
  })

  test("strips email addresses from Name <email> format", () => {
    expect(formatAuthor("Darren Okafor <darren@fizzandfuel.com>")).toBe("Darren Okafor")
  })

  test("strips emails from multi-author with Name <email>", () => {
    expect(
      formatAuthor("GitHub <notifications@github.com>, Darren Okafor <darren@fizzandfuel.com>")
    ).toBe("GitHub, Darren Okafor")
  })

  test("handles mixed formats", () => {
    expect(
      formatAuthor("Dr. Anita Rowe <anita.rowe@flavorworks.com>, Darren Okafor <darren@fizzandfuel.com>, Leo Park")
    ).toBe("Dr. Anita Rowe, Darren Okafor, and 1 other")
  })

  test("falls back to email when no name present", () => {
    expect(formatAuthor("<notifications@github.com>")).toBe("notifications@github.com")
  })

  test("falls back to email in multi-author with bare email", () => {
    expect(formatAuthor("<no-reply@example.com>, Darren Okafor <darren@fizzandfuel.com>")).toBe(
      "no-reply@example.com, Darren Okafor"
    )
  })

  test("handles plain email without angle brackets", () => {
    expect(formatAuthor("notifications@github.com")).toBe("notifications@github.com")
  })
})

describe("resultNavigationUrl", () => {
  test("deep-links a decision result to its comment via the #comment-<id> hash", () => {
    const result = fakeResult({
      content_type: "decision",
      source_url: "/posts/abc",
      metadata: { comment_gid: "gid://convictional/PostComment/xyz-123" },
    })
    expect(resultNavigationUrl(result)).toBe("/posts/abc#comment-xyz-123")
  })

  test("returns the plain source_url for a non-decision result", () => {
    expect(resultNavigationUrl(fakeResult({ content_type: "post" }))).toBe("/posts/abc")
  })

  test("returns the plain source_url for a decision missing its comment_gid", () => {
    expect(resultNavigationUrl(fakeResult({ content_type: "decision", metadata: {} }))).toBe("/posts/abc")
  })
})
