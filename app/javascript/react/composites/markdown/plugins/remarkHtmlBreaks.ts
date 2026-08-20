import type { Break, Html, Root } from "mdast"
import type { Plugin } from "unified"
import type { Parent } from "unist"
import { visit } from "unist-util-visit"

// The editor serializes a blank line between paragraphs as a literal `<br />`
// (richText/schema/paragraphFormatting.ts), but react-markdown drops raw HTML.
// Converting just these to mdast `break` nodes renders a real `<br>` (allowed by
// the sanitizer) without enabling raw-HTML parsing for the whole document, which
// rehype-raw would do — and that mangles remarkMentions' data-name spans.
const BR_PATTERN = /^<br\s*\/?>$/i

export const remarkHtmlBreaks: Plugin<[], Root> = () => {
  return tree => {
    visit(tree, "html", (node: Html, index, parent) => {
      if (!parent || index === undefined) return
      if (BR_PATTERN.test(node.value.trim())) {
        const lineBreak: Break = { type: "break" }
        ;(parent as Parent).children.splice(index, 1, lineBreak)
      }
    })
  }
}
