import { describe, expect, test } from "vitest"

import { markdownToPlainText } from "../../../../../app/javascript/react/composites/markdown/toPlainText"

describe("markdownToPlainText", () => {
  describe("basic conversion", () => {
    test("strips inline formatting symbols", () => {
      expect(markdownToPlainText("**bold** and *italic*")).toBe("bold and italic")
    })

    test("returns empty string for empty input", () => {
      expect(markdownToPlainText("")).toBe("")
    })
  })

  describe("custom syntax", () => {
    test("converts @[Alice] to @Alice", () => {
      expect(markdownToPlainText("Hi @[Alice], welcome.")).toBe("Hi @Alice, welcome.")
    })

    test("deletes [^content:UUID] markers", () => {
      const out = markdownToPlainText("Before [^content:abc-123-def] after.")
      expect(out).toContain("Before")
      expect(out).toContain("after")
      expect(out).not.toContain("[^")
      expect(out).not.toContain("content:")
    })

    test("handles truncated [^content:ab without crash", () => {
      const out = markdownToPlainText("Before [^content:ab")
      expect(out).not.toContain("[^")
      expect(out).not.toContain("content:")
      expect(out).toContain("Before")
    })

    test("handles bare *bo without crash", () => {
      // The function should either preserve the literal or strip the marker;
      // we just assert no crash and a non-empty sensible result.
      const out = markdownToPlainText("*bo")
      expect(typeof out).toBe("string")
      expect(out).toContain("bo")
    })
  })

  describe("whitespace collapse", () => {
    test("collapses whitespace by default", () => {
      const out = markdownToPlainText("hello\n\n\nworld   tab\there")
      expect(out).toBe("hello world tab here")
    })

    test("collapse: false preserves newlines", () => {
      const out = markdownToPlainText("line one\n\nline two", { collapse: false })
      expect(out).toContain("\n")
      expect(out).toContain("line one")
      expect(out).toContain("line two")
    })
  })

  describe("maxLength", () => {
    test("truncates with ellipsis when over maxLength, reserving a slot for the ellipsis", () => {
      // "hello world" is 11 chars; maxLength 5 -> slice 4 = "hell", + "…" -> "hell…" (5 chars).
      expect(markdownToPlainText("hello world", { maxLength: 5 })).toBe("hell…")
    })

    test("trims trailing whitespace before the ellipsis", () => {
      // "abcde fghij" -> slice 5 = "abcde", trimEnd -> "abcde", + "…" -> "abcde…" (6 chars).
      expect(markdownToPlainText("abcde fghij", { maxLength: 6 })).toBe("abcde…")
    })

    test("output length never exceeds maxLength", () => {
      const out = markdownToPlainText("a".repeat(500), { maxLength: 200 })
      expect(out.length).toBe(200)
      expect(out.endsWith("…")).toBe(true)
    })

    test("returns empty string for maxLength: 0 (no infinite loop, no crash)", () => {
      expect(markdownToPlainText("hello", { maxLength: 0 })).toBe("")
    })

    test("does not truncate when result is shorter than maxLength", () => {
      expect(markdownToPlainText("hi", { maxLength: 100 })).toBe("hi")
    })
  })

  describe("code fences", () => {
    test("extracts the code text without backticks or language tag", () => {
      const source = "```js\nconsole.log('hi')\n```"
      const out = markdownToPlainText(source)
      expect(out).toContain("console.log('hi')")
      expect(out).not.toContain("`")
      expect(out).not.toContain("```")
    })

    test("separates paragraph from following code block with a space under default collapse", () => {
      const out = markdownToPlainText("First paragraph.\n\n```\nsome code\n```")
      expect(out).toBe("First paragraph. some code")
    })

    test("separates paragraph from following code block with blank line when collapse: false", () => {
      const out = markdownToPlainText("First paragraph.\n\n```\nsome code\n```", { collapse: false })
      expect(out).toBe("First paragraph.\n\nsome code")
    })

    test("separates code block from following paragraph symmetrically", () => {
      const out = markdownToPlainText("```\nsome code\n```\n\nSecond paragraph.", { collapse: false })
      expect(out).toBe("some code\n\nSecond paragraph.")
    })

    test("inline code does not introduce a block separator", () => {
      const out = markdownToPlainText("before `snippet` after", { collapse: false })
      expect(out).toBe("before snippet after")
    })
  })

  describe("chat preview specifics", () => {
    test("hard break produces a newline when collapse: false", () => {
      const out = markdownToPlainText("hello\\\nworld", { collapse: false })
      expect(out).toBe("hello\nworld")
    })

    test("hard break collapses to a single space when collapse: true", () => {
      const out = markdownToPlainText("hello\\\nworld")
      expect(out).toBe("hello world")
    })
  })

  describe("images", () => {
    test("substitutes an image node with its alt text or a generic placeholder", () => {
      // First three mirror tests/unit/lib/test_markdown.py:25-31 (parity with Python).
      expect(markdownToPlainText("![](https://example.com/cat.png)")).toBe("[image]")
      expect(markdownToPlainText("![a cat](https://example.com/cat.png)")).toBe("[a cat]")
      expect(markdownToPlainText("look ![logo](https://x.com/l.png) here")).toBe("look [logo] here")
      // JS-only edge: empty-alt inline mix.
      expect(markdownToPlainText("look ![](https://x.com/l.png) here")).toBe("look [image] here")
    })
  })

  describe("tables", () => {
    // Without tableCell in BLOCK_TYPES, a row "| 1 | 2 | 3 |" walks as
    // cell→"1", cell→"2", cell→"3" with no separator between them and
    // collapses into "123".
    const source = "| a | b | c |\n| - | - | - |\n| 1 | 2 | 3 |"

    test("separates row cells with whitespace under default collapse", () => {
      const out = markdownToPlainText(source)
      expect(out).toContain("1 2 3")
      expect(out).not.toContain("123")
    })

    test("preserves cell separation when collapse: false", () => {
      const out = markdownToPlainText(source, { collapse: false })
      expect(out).not.toMatch(/123/)
      expect(out).toContain("1")
      expect(out).toContain("2")
      expect(out).toContain("3")
    })
  })
})
