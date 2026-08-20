import { describe, expect, test } from "vitest"
import { builders } from "prosemirror-test-builder"

import { isBlankMarkdown, parse, schema, serialize } from "../../../../app/javascript/richText/schema"
import cases from "../../../fixtures/markdown_whitespace/cases.json"

const { doc, paragraph, heading, hard_break } = builders(schema)

const NBSP = String.fromCharCode(0xa0)

// The rejected inline-<br/> encoding loses data on parse by design; the indented
// code block is legacy/paste input the editor never emits (it serializes to a fenced
// block); the `legacy` fixtures are pre-migration stored content (old &#x20; leading
// spaces, non-self-closing <br>) that the serializer re-normalizes to today's wire.
// None are frozen editor output, so they are exempt from the wire-equality assertion
// below — but all must still reach a stable fixed point.
const NOT_FROZEN_EDITOR_OUTPUT = new Set([
  "single_hard_break_inline_br",
  "code_block_indented",
  "legacy_leading_spaces_x20",
  "legacy_empty_paragraph_bare_br",
  // Renderer-only conformance fixtures: an all-whitespace code block and bare
  // soft breaks (in a paragraph, and between inline elements). The editor never
  // emits any of these (breaks serialize as the hard-break token), so they
  // aren't frozen editor output.
  "code_block_all_whitespace",
  "soft_break_paragraph",
  "em_soft_em",
  "link_soft_em",
])
// Parsing this deliberately drops content (documented data loss), so it has no fixed point.
const LOSSY_BY_DESIGN = new Set(["single_hard_break_inline_br"])

describe("whitespace fidelity cases — PR1 lossless serialization", () => {
  test("every case's wire round-trips to a stable fixed point", () => {
    // The PR1 guarantee: serialize(parse(x)) is idempotent, so re-editing never
    // progressively corrupts content (the double-backslash / setext family of bugs).
    for (const c of cases.cases) {
      if (LOSSY_BY_DESIGN.has(c.name)) continue
      const once = serialize(parse(c.wire))
      const twice = serialize(parse(once))
      expect(twice, `${c.name}: round-trip is not a fixed point`).toBe(once)
    }
  })

  test("frozen wire equals the serializer's canonical output", () => {
    // Each frozen wire IS the editor serializer's output — parse then re-serialize
    // reproduces it byte-for-byte. This pins the wire so PR2/PR3/PR4 build against a
    // stable contract.
    for (const c of cases.cases) {
      if (NOT_FROZEN_EDITOR_OUTPUT.has(c.name)) continue
      expect(serialize(parse(c.wire)), `${c.name}: wire is not the serializer's canonical form`).toBe(c.wire)
    }
  })
})

describe("PR1 serializer fixes", () => {
  test("lone empty paragraph serializes to <br /> (was silently dropped to '')", () => {
    expect(serialize(doc(paragraph("")))).toBe("<br />\n")
    // Round-trips: a one-blank-line doc no longer renders as nothing.
    expect(serialize(parse("<br />\n"))).toBe("<br />\n")
  })

  test("leading spaces become NBSP; interior runs stay literal", () => {
    expect(serialize(doc(paragraph("   text")))).toBe(`${NBSP}${NBSP}${NBSP}text\n`)
    // 4+ leading spaces would trip the indented-code-block rule as literal spaces; NBSP is safe.
    expect(serialize(doc(paragraph("    text")))).toBe(`${NBSP}${NBSP}${NBSP}${NBSP}text\n`)
    // Interior run is untouched — pre-wrap preserves it, NBSP is only for leading position.
    expect(serialize(doc(paragraph("a   b")))).toBe("a   b\n")
    // Leading NBSP round-trips losslessly.
    expect(serialize(parse(`${NBSP}${NBSP}${NBSP}text\n`))).toBe(`${NBSP}${NBSP}${NBSP}text\n`)
  })

  test("heading + hard break stays ATX with the break flattened to a space (no data loss)", () => {
    // Previously an h1/h2 with a break serialized to a setext underline that re-parsed
    // to an empty document — total data loss. Now it flattens to ATX and both lines survive.
    expect(serialize(doc(heading({ level: 1 }, "H", hard_break(), "x")))).toBe("# H x\n")
    expect(serialize(doc(heading({ level: 2 }, "H", hard_break(), "x")))).toBe("## H x\n")
    const roundTripped = parse(serialize(doc(heading({ level: 1 }, "H", hard_break(), "x"))))
    expect(roundTripped.textContent).toBe("H x")
  })
})

describe("isBlankMarkdown", () => {
  test("treats empty and <br />-only content as blank", () => {
    expect(isBlankMarkdown("")).toBe(true)
    expect(isBlankMarkdown("<br />\n")).toBe(true)
    expect(isBlankMarkdown("<br />\n\n<br />\n")).toBe(true)
    expect(isBlankMarkdown("   \n")).toBe(true)
  })

  test("treats real content (text, images, mentions) as non-blank", () => {
    expect(isBlankMarkdown("hello\n")).toBe(false)
    expect(isBlankMarkdown("![alt](https://example.com/x.png)\n")).toBe(false)
    expect(isBlankMarkdown("@[John Doe]\n")).toBe(false)
    // A blank composer's own serialized output is recognised as blank.
    expect(isBlankMarkdown(serialize(doc(paragraph(""))))).toBe(true)
  })
})
