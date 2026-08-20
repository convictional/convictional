import type { Element, Root as HastRoot, RootContent, Text } from "hast"
import type { Root } from "mdast"
import remarkParse from "remark-parse"
import type { Plugin } from "unified"
import { unified } from "unified"
import type { Node, Parent } from "unist"
import { describe, expect, test } from "vitest"

import { rehypeRestoreAlign } from "../../../../../app/javascript/react/composites/markdown/plugins/rehypeRestoreAlign"
import { rehypeStripBreakNewlines } from "../../../../../app/javascript/react/composites/markdown/plugins/rehypeStripBreakNewlines"
import { rehypeWrapEmptyParagraphs } from "../../../../../app/javascript/react/composites/markdown/plugins/rehypeWrapEmptyParagraphs"
import { remarkContentCitation, remarkMentions } from "../../../../../app/javascript/react/composites/markdown/plugins"

interface MdastDataNode extends Node {
  type: string
  value?: string
  data?: {
    hName?: string
    hProperties?: Record<string, unknown>
  }
  children?: MdastDataNode[]
}

function parse(source: string, plugins: Array<Plugin<[], Root>> = []): MdastDataNode {
  const processor = unified().use(remarkParse)
  for (const plugin of plugins) processor.use(plugin)
  return processor.runSync(processor.parse(source)) as MdastDataNode
}

function walk(node: MdastDataNode, visit: (n: MdastDataNode) => void) {
  visit(node)
  const children = (node as unknown as Parent).children
  if (Array.isArray(children)) {
    for (const child of children as MdastDataNode[]) walk(child, visit)
  }
}

function findAll(node: MdastDataNode, predicate: (n: MdastDataNode) => boolean): MdastDataNode[] {
  const out: MdastDataNode[] = []
  walk(node, n => {
    if (predicate(n)) out.push(n)
  })
  return out
}

function collectText(node: MdastDataNode): string {
  let text = ""
  walk(node, n => {
    if (typeof n.value === "string") text += n.value
  })
  return text
}

function isMentionNode(n: MdastDataNode): boolean {
  const data = n.data
  if (!data) return false
  if (data.hName !== "span") return false
  const className = data.hProperties?.className
  return Array.isArray(className) && className.includes("mention")
}

describe("remarkMentions", () => {
  test("@[Alice] becomes a HAST-targeted span with class 'mention' and data-name", () => {
    const tree = parse("Hi @[Alice]!", [remarkMentions])
    const mentions = findAll(tree, isMentionNode)
    expect(mentions).toHaveLength(1)

    const node = mentions[0]
    expect(node.data?.hName).toBe("span")
    const className = node.data?.hProperties?.className
    expect(Array.isArray(className)).toBe(true)
    expect(className).toContain("mention")
    expect(node.data?.hProperties?.["data-name"]).toBe("Alice")
  })

  test("preserves apostrophes in data-name", () => {
    const tree = parse("@[O'Brien] arrived.", [remarkMentions])
    const mentions = findAll(tree, isMentionNode)
    expect(mentions).toHaveLength(1)
    expect(mentions[0].data?.hProperties?.["data-name"]).toBe("O'Brien")
  })

  test("renders inside strong without crashing", () => {
    const tree = parse("**@[Alice]**", [remarkMentions])
    const mentions = findAll(tree, isMentionNode)
    expect(mentions).toHaveLength(1)
    expect(mentions[0].data?.hProperties?.["data-name"]).toBe("Alice")

    // The mention node should live inside a strong node.
    const strongNodes = findAll(tree, n => n.type === "strong")
    expect(strongNodes).toHaveLength(1)
    const strongMentions = findAll(strongNodes[0], isMentionNode)
    expect(strongMentions).toHaveLength(1)
  })
})

describe("remarkContentCitation", () => {
  test("[^content:UUID] is deleted from the AST entirely", () => {
    const tree = parse("Before [^content:abc-12345-678-9012-345678901234] after.", [remarkContentCitation])
    const text = collectText(tree)
    expect(text).not.toContain("[^")
    expect(text).not.toContain("content:")
    expect(text).not.toContain("abc-12345")
    expect(text).toContain("Before")
    expect(text).toContain("after")

    // No node should be marked as a content-citation in the output.
    const citationNodes = findAll(tree, n => n.type === "contentCitation" || n.type === "content_citation")
    expect(citationNodes).toHaveLength(0)
  })

  test("truncated [^content:ab is deleted without crashing", () => {
    const tree = parse("Before [^content:ab", [remarkContentCitation])
    const text = collectText(tree)
    expect(text).not.toContain("[^")
    expect(text).not.toContain("content:")
    expect(text.trim()).toBe("Before")
  })

  test("'Foo [^.* bar' bracket form is deleted from output", () => {
    const tree = parse("Foo [^.* bar", [remarkContentCitation])
    const text = collectText(tree)
    expect(text).not.toContain("[^")
    expect(text).toContain("Foo")
    expect(text).toContain("bar")
  })

  test("truncated [^foo (no closing bracket, no 'content:' prefix) is deleted", () => {
    // Mirrors the server's `INCOMPLETE_FOOTNOTE_PATTERN` safety net: any
    // `[^...` stub that survives parsing should be scrubbed, not just the
    // `[^content:` and `[^.` shapes we expect from LLM output today.
    const tree = parse("Before [^foo", [remarkContentCitation])
    const text = collectText(tree)
    expect(text).not.toContain("[^")
    expect(text.trim()).toBe("Before")
  })

  test("'[^abc bar' fragment is bounded at the next whitespace", () => {
    // The regex stops at whitespace so it can't swallow trailing prose if a
    // stray `[^` appears mid-paragraph.
    const tree = parse("foo [^abc bar", [remarkContentCitation])
    const text = collectText(tree)
    expect(text).not.toContain("[^")
    expect(text).not.toContain("abc")
    expect(text).toContain("foo")
    expect(text).toContain("bar")
  })

  test("preserves whitespace at the boundary of a text node when citation is removed", () => {
    // Pass 2 must not over-trim: when a citation sits at the end of a text
    // node (e.g., before an inline `**bar**`), removing it leaves a trailing
    // space that the next inline element relies on for word separation.
    // A `.trim()` after the regex replace would eat that space and produce
    // "foo**bar**" rendered as "foobar".
    const tree = parse("foo [^content:abc] **bar**", [remarkContentCitation])
    const text = collectText(tree)
    // Both surrounding spaces survive (regex replaces only the citation token).
    // The previous `.trim()` would have collapsed this to "foobar".
    expect(text).toBe("foo  bar")
    expect(text.startsWith("foo ")).toBe(true)
  })

  test("paragraph containing only a citation collapses to an empty paragraph", () => {
    // This is the case the simplicity reviewer flagged: a paragraph whose
    // only child is the citation. After scrubbing, the paragraph still
    // exists with a single empty text child. We don't sweep it because the
    // server's incomplete_footnote plugin produces the same shape, and
    // empty text renders as nothing in react-markdown.
    const tree = parse("[^content:abc]", [remarkContentCitation])
    const text = collectText(tree)
    expect(text).toBe("")
  })
})

describe("rehypeRestoreAlign", () => {
  function makeCell(tagName: "td" | "th", align?: string): Element {
    return {
      type: "element",
      tagName,
      properties: align === undefined ? {} : { align },
      children: [],
    }
  }

  function runPlugin(nodes: Element[]): HastRoot {
    const tree: HastRoot = { type: "root", children: nodes }
    rehypeRestoreAlign()(tree)
    return tree
  }

  test("moves align onto data-align and removes the original property", () => {
    const td = makeCell("td", "center")
    const th = makeCell("th", "right")
    runPlugin([td, th])

    expect(td.properties?.["data-align"]).toBe("center")
    expect("align" in (td.properties ?? {})).toBe(false)
    expect(th.properties?.["data-align"]).toBe("right")
    expect("align" in (th.properties ?? {})).toBe(false)
  })

  test("ignores cells without an align property", () => {
    const td = makeCell("td")
    runPlugin([td])

    expect(td.properties?.["data-align"]).toBeUndefined()
    expect("align" in (td.properties ?? {})).toBe(false)
  })

  test("ignores unknown align values and leaves the original alone", () => {
    // Defensive: only the three remark-gfm-emitted values are translated.
    const td = makeCell("td", "justify")
    runPlugin([td])

    expect(td.properties?.["data-align"]).toBeUndefined()
    expect(td.properties?.align).toBe("justify")
  })
})

function text(value: string): Text {
  return { type: "text", value }
}
function el(tagName: string, children: RootContent[] = []): Element {
  return { type: "element", tagName, properties: {}, children }
}

describe("rehypeStripBreakNewlines", () => {
  function run(children: RootContent[]): RootContent[] {
    const tree: HastRoot = { type: "root", children }
    rehypeStripBreakNewlines()(tree)
    return tree.children
  }

  test("drops the cosmetic \\n node that follows a hard break, keeping real text", () => {
    // hardBreak emits [<br>, {text:"\n"}]; under pre-wrap the \n doubles the break.
    const p = el("p", [text("a"), el("br"), text("\n"), text("b")])
    run([p])
    expect(p.children).toEqual([text("a"), el("br"), text("b")])
  })

  test("drops inter-block pretty-print newlines between siblings", () => {
    const out = run([el("p", [text("A")]), text("\n"), el("p", [text("B")])])
    expect(out).toEqual([el("p", [text("A")]), el("p", [text("B")])])
  })

  test("preserves authored space runs and soft-break newlines embedded in mixed text", () => {
    // The surgical boundary: only whitespace-only nodes containing a newline are
    // serializer artifacts. A space run and a soft break both live inside mixed
    // text nodes and must survive verbatim.
    const spaceRun = el("p", [text("a   b")])
    const softBreak = el("p", [text("a\nb")])
    run([spaceRun, softBreak])
    expect(spaceRun.children).toEqual([text("a   b")])
    expect(softBreak.children).toEqual([text("a\nb")])
  })

  test("leaves a pure-NBSP node alone (leading spaces are U+00A0, not ASCII whitespace)", () => {
    const p = el("p", [text("   ")])
    run([p])
    expect(p.children).toEqual([text("   ")])
  })
  test("preserves a standalone soft-break newline between two inline siblings", () => {
    // `*foo*\n*bar*` parses to p[em, "\n", em] — the soft break's \n is its own
    // whitespace-only node here, not embedded in mixed text. Stripping it would
    // weld the spans into "foobar" (the bug flagged on PR #8732). Under pre-wrap
    // the \n is the author's intended line break, so it must survive.
    const p = el("p", [el("em", [text("foo")]), text("\n"), el("em", [text("bar")])])
    run([p])
    expect(p.children).toEqual([el("em", [text("foo")]), text("\n"), el("em", [text("bar")])])
  })

  test("preserves a soft-break newline between any two inline siblings (link + em)", () => {
    const p = el("p", [el("a", [text("a")]), text("\n"), el("em", [text("bar")])])
    run([p])
    expect(p.children).toEqual([el("a", [text("a")]), text("\n"), el("em", [text("bar")])])
  })

  test("still strips a block-level neighbor newline inside a loose list item", () => {
    // A loose <li> holds <p> blocks; the newline between them is pretty-print,
    // not a soft break, even though its parent (<li>) can hold inline content.
    const li = el("li", [el("p", [text("a")]), text("\n"), el("p", [text("b")])])
    run([li])
    expect(li.children).toEqual([el("p", [text("a")]), el("p", [text("b")])])
  })

  test("still strips whitespace newlines directly under a block container (ul)", () => {
    // Adjacent inline-ish neighbors (text nodes) don't rescue a newline whose
    // parent is a block container — those are always structural pretty-print.
    const ul = el("ul", [text("\n"), el("li", [text("a")]), text("\n"), el("li", [text("b")]), text("\n")])
    run([ul])
    expect(ul.children).toEqual([el("li", [text("a")]), el("li", [text("b")])])
  })
})

describe("rehypeWrapEmptyParagraphs", () => {
  function run(children: RootContent[]): RootContent[] {
    const tree: HastRoot = { type: "root", children }
    rehypeWrapEmptyParagraphs()(tree)
    return tree.children
  }

  test("wraps a root-level <br> (empty paragraph) in a <p>", () => {
    const out = run([el("p", [text("A")]), el("br"), el("p", [text("B")])])
    expect(out).toEqual([el("p", [text("A")]), el("p", [el("br")]), el("p", [text("B")])])
  })

  test("leaves an inline <br> inside a paragraph untouched (the hard-break token)", () => {
    const p = el("p", [text("a"), el("br"), text("b")])
    run([p])
    expect(p.children).toEqual([text("a"), el("br"), text("b")])
  })
})
