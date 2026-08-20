import { expect, test, describe } from "vitest"

import { detectLinkHref } from "../../../../../app/javascript/react/composites/editor/features/linkUrls"

describe("detectLinkHref", () => {
  test("uses URL with https scheme as-is", () => {
    expect(detectLinkHref("https://example.com")).toBe("https://example.com")
    expect(detectLinkHref("https://example.com/path")).toBe("https://example.com/path")
    expect(detectLinkHref("https://example.com/path?query=1")).toBe("https://example.com/path?query=1")
  })

  test("uses URL with http scheme as-is", () => {
    expect(detectLinkHref("http://example.com")).toBe("http://example.com")
    expect(detectLinkHref("http://example.com/path")).toBe("http://example.com/path")
  })

  test("prepends https:// to domain-like text", () => {
    expect(detectLinkHref("example.com")).toBe("https://example.com")
    expect(detectLinkHref("www.example.com")).toBe("https://www.example.com")
    expect(detectLinkHref("docs.google.com")).toBe("https://docs.google.com")
    expect(detectLinkHref("sub.domain.co.uk")).toBe("https://sub.domain.co.uk")
  })

  test("prepends https:// to domain with path", () => {
    expect(detectLinkHref("example.com/path")).toBe("https://example.com/path")
    expect(detectLinkHref("docs.google.com/document/d/123")).toBe("https://docs.google.com/document/d/123")
  })

  test("prepends https:// to domain with query string", () => {
    expect(detectLinkHref("example.com?query=1")).toBe("https://example.com?query=1")
    expect(detectLinkHref("google.com/search?q=test")).toBe("https://google.com/search?q=test")
  })

  test("returns default for text with spaces", () => {
    expect(detectLinkHref("hello world")).toBe("https://example.com")
    expect(detectLinkHref("not a url")).toBe("https://example.com")
  })

  test("returns default for plain text without domain pattern", () => {
    expect(detectLinkHref("hello")).toBe("https://example.com")
    expect(detectLinkHref("some text")).toBe("https://example.com")
  })

  test("returns default for single letter TLD", () => {
    expect(detectLinkHref("file.a")).toBe("https://example.com")
  })
})
