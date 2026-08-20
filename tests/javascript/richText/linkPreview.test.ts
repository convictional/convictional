import { expect, test, describe } from "vitest"
import { findPreviewUrl } from "../../../app/javascript/richText/linkPreview"

describe("findPreviewUrl", () => {
  test("finds bare URLs", () => {
    expect(findPreviewUrl("Check out https://example.com")).toBe("https://example.com")
  })

  test("finds markdown link URLs", () => {
    expect(findPreviewUrl("[example](https://example.com)")).toBe("https://example.com")
  })

  test("returns null for empty content", () => {
    expect(findPreviewUrl("")).toBeNull()
  })

  test("returns null for content without URLs", () => {
    expect(findPreviewUrl("just some text")).toBeNull()
  })

  test("ignores image markdown", () => {
    expect(findPreviewUrl("![](https://img.example.com/photo.jpg)")).toBeNull()
  })

  test("ignores image markdown with alt text", () => {
    expect(findPreviewUrl("![alt text](https://img.example.com/photo.jpg)")).toBeNull()
  })

  test("finds link URL when image is also present", () => {
    expect(findPreviewUrl("![](https://img.example.com/photo.jpg)\n\nhttps://example.com")).toBe(
      "https://example.com"
    )
  })

  test("ignores bare image URLs", () => {
    expect(findPreviewUrl("https://example.com/photo.jpg")).toBeNull()
    expect(findPreviewUrl("https://example.com/photo.png")).toBeNull()
    expect(findPreviewUrl("https://example.com/photo.gif")).toBeNull()
    expect(findPreviewUrl("https://example.com/photo.webp")).toBeNull()
    expect(findPreviewUrl("https://example.com/photo.svg")).toBeNull()
  })

  test("ignores image URLs with query strings", () => {
    expect(findPreviewUrl("https://example.com/photo.jpg?w=800")).toBeNull()
  })

  test("ignores markdown links pointing to images", () => {
    expect(findPreviewUrl("[photo](https://example.com/photo.png)")).toBeNull()
  })

  test("finds non-image URL when it comes before an image URL", () => {
    expect(
      findPreviewUrl("https://example.com/article\n\nhttps://example.com/photo.jpg")
    ).toBe("https://example.com/article")
  })

  test("strips trailing sentence punctuation", () => {
    expect(findPreviewUrl("see https://example.com.")).toBe("https://example.com")
    expect(findPreviewUrl("see https://example.com/article, then reply")).toBe("https://example.com/article")
  })

  test("still ignores image URLs ending a sentence", () => {
    expect(findPreviewUrl("see https://example.com/photo.png.")).toBeNull()
  })

  // Mirror the cases in tests/unit/presenters/test_links.py so the compose-time
  // preview and the submit-time server unfurl extract the same URL.
  test("preserves balanced parentheses in URLs", () => {
    const parenUrl = "https://en.wikipedia.org/wiki/Scheme_(programming_language)"
    expect(findPreviewUrl(parenUrl)).toBe(parenUrl)
    expect(findPreviewUrl(`[Scheme](${parenUrl})`)).toBe(parenUrl)
    // Legacy serialized form with backslash-escaped parens
    expect(
      findPreviewUrl("[Scheme](https://en.wikipedia.org/wiki/Scheme_\\(programming_language\\))")
    ).toBe(parenUrl)
  })

  test("drops a wrapping paren from prose", () => {
    expect(findPreviewUrl("(https://example.com)")).toBe("https://example.com")
    expect(findPreviewUrl("see https://en.wikipedia.org/wiki/Foo_(bar).")).toBe(
      "https://en.wikipedia.org/wiki/Foo_(bar)"
    )
  })
})
