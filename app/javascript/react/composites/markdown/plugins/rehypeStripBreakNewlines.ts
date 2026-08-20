import type { Root, RootContent } from "hast"
import type { Plugin } from "unified"
import { SKIP, visit } from "unist-util-visit"

// mdast-util-to-hast's hard-break handler emits a `<br>` element *followed by a
// standalone `"\n"` text node*, and remark-rehype pretty-prints a `"\n"` text
// node between every pair of block siblings. Both are invisible under the prose
// default `white-space: normal`, but the text-bearing blocks now carry
// `white-space: pre-wrap` (markdown-content.css) — under which that cosmetic
// `\n` becomes a *visible* second line break, doubling every hard break.
// Stripping it here keeps the `pre-wrap` CSS rule from needing an exception for
// the cosmetic newline that mdast-util-to-hast pairs with every `<br>`.
//
// The strip is position-aware, because one whitespace-only `\n` shape is NOT a
// serializer artifact: a soft break (a bare source newline) between two adjacent
// *inline* elements — e.g. `*foo*\n*bar*` → `p[em, "\n", em]` — is a standalone
// whitespace-only text node too, but its `\n` is authored content that pre-wrap
// should render as the intended line break. Dropping it welds the spans
// (`foobar`). So a whitespace-only `\n` node is removed only when it is a
// serializer artifact: adjacent to a `<br>` (the cosmetic hard-break newline),
// or sitting between/at the edge of block-level content (inter-block
// pretty-print). It is preserved when it sits between inline siblings inside a
// phrasing container — the soft-break case. Authored space runs and text-adjacent
// soft breaks are never affected regardless: they live inside mixed text nodes
// (`"a   b"`, `"a\nb"`), and leading NBSP is U+00A0 (outside `[ \t\r\n]`).
const COSMETIC_WHITESPACE = /^[ \t\r\n]*\n[ \t\r\n]*$/

// HTML block-level elements our Markdown can emit. A whitespace-only `\n` node
// touching one of these (as a sibling) is inter-block pretty-print, not a soft
// break — this also catches loose-list items whose children are `<p>` blocks.
const BLOCK_LEVEL_TAGS = new Set([
  "p",
  "div",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "ul",
  "ol",
  "li",
  "dl",
  "dt",
  "dd",
  "table",
  "thead",
  "tbody",
  "tfoot",
  "tr",
  "td",
  "th",
  "blockquote",
  "pre",
  "hr",
  "figure",
  "figcaption",
])

// Elements whose direct children are inline/phrasing content — the only place a
// soft break between inline siblings can legitimately appear. Whitespace `\n`
// directly under a block container (root, `<ul>`, `<table>`, …) is always
// structural pretty-print.
const PHRASING_CONTAINERS = new Set([
  "p",
  "li",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "td",
  "th",
  "a",
  "em",
  "strong",
  "del",
  "ins",
  "sup",
  "sub",
  "code",
  "span",
  "mark",
  "s",
  "u",
  "b",
  "i",
])

function isBreak(node: RootContent | undefined): boolean {
  return !!node && node.type === "element" && node.tagName === "br"
}

function isInlineContent(node: RootContent | undefined): boolean {
  if (!node) return false
  if (node.type === "text") return true
  if (node.type === "element") return !BLOCK_LEVEL_TAGS.has(node.tagName)
  return false
}

export const rehypeStripBreakNewlines: Plugin<[], Root> = () => {
  return tree => {
    visit(tree, (node, index, parent) => {
      // <pre>/<code> content is verbatim and exempt from all whitespace handling
      // (the whitespace contract). Skip their whole subtree so an all-whitespace
      // code block — one whitespace-only text node — is never mistaken for a
      // cosmetic newline and spliced away.
      if (node.type === "element" && (node.tagName === "pre" || node.tagName === "code")) {
        return SKIP
      }
      if (node.type !== "text" || !parent || index === undefined) return
      if (!COSMETIC_WHITESPACE.test(node.value)) return

      const prev = parent.children[index - 1] as RootContent | undefined
      const next = parent.children[index + 1] as RootContent | undefined

      // A soft break between two inline siblings inside a phrasing container is
      // authored content — under pre-wrap its `\n` renders as the intended line
      // break, so keep it. The cosmetic hard-break newline (adjacent to a `<br>`)
      // and inter-block pretty-print (a block-level neighbor, or a non-phrasing
      // parent like root/`<ul>`) are serializer artifacts and fall through to the
      // strip below.
      const isSoftBreakBetweenInline =
        parent.type === "element" &&
        PHRASING_CONTAINERS.has(parent.tagName) &&
        !isBreak(prev) &&
        !isBreak(next) &&
        isInlineContent(prev) &&
        isInlineContent(next)
      if (isSoftBreakBetweenInline) return

      parent.children.splice(index, 1)
      return [SKIP, index]
    })
  }
}
