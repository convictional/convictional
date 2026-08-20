import type { Root, Text } from "mdast"
import type { Plugin } from "unified"
import type { Node, Parent } from "unist"
import { SKIP, visit } from "unist-util-visit"

// Mirrors the server's `content_citations` + `incomplete_footnote` plugins
// from app/helpers/markdown.py.

// Catches citation fragments that survive as plain text — truncated streaming
// output (`[^foo`), the `[^.*` bracket form, or any other unclosed `[^...`
// stub. Mirrors the server's `INCOMPLETE_FOOTNOTE_PATTERN = r"\[\^.*"` net,
// but bounded to non-whitespace, non-`]` chars so a stray `[^` can't swallow
// the rest of a paragraph across newlines or citation boundaries.
// Well-formed `[^content:UUID]` parses as a footnoteReference and is handled
// in pass 1; the plugin order in ./index.ts ensures remark-gfm runs first.
const CITATION_FRAGMENT = /\[\^/
const CITATION_FRAGMENT_GLOBAL = /\[\^[^\s\]]*\]?/g

function isContentCitation(node: Node): boolean {
  return (
    (node.type === "footnoteReference" || node.type === "footnoteDefinition") &&
    "identifier" in node &&
    typeof node.identifier === "string" &&
    node.identifier.startsWith("content:")
  )
}

export const remarkContentCitation: Plugin<[], Root> = () => {
  return tree => {
    // Pass 1: drop content-citation footnote nodes (well-formed `[^content:UUID]`).
    visit(tree, (node, index, parent) => {
      if (!parent || index === undefined) return
      if (isContentCitation(node)) {
        ;(parent as Parent).children.splice(index, 1)
        return [SKIP, index]
      }
    })

    // Pass 2: scrub literal citation fragments. No `.trim()` — it would eat
    // legitimate whitespace adjacent to a citation (" leading [^content:x] ").
    visit(tree, "text", (node: Text) => {
      if (CITATION_FRAGMENT.test(node.value)) {
        node.value = node.value.replace(CITATION_FRAGMENT_GLOBAL, "")
      }
    })
  }
}
