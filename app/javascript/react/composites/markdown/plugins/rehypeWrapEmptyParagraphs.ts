import type { Element, Root, RootContent } from "hast"
import type { Plugin } from "unified"

// The wire encodes an empty paragraph (a blank line in a blank-line run) as a
// standalone `<br />` on its own line. remarkHtmlBreaks turns it into an mdast
// `break`, which remark-rehype lifts to a bare `<br>` at the document root. The
// whitespace contract's canonical empty block is a *wrapped* `<p><br></p>`,
// exactly 1:1 with each empty paragraph — so wrap every root-level `<br>`.
//
// Only root-level breaks are empty paragraphs. An inline hard break (the
// `a\<newline>b` token) stays a `<br>` *inside* its `<p>`, so it is never a
// child of the root and is correctly left alone.
export const rehypeWrapEmptyParagraphs: Plugin<[], Root> = () => {
  return tree => {
    tree.children = tree.children.map((child): RootContent => {
      if (child.type === "element" && child.tagName === "br") {
        const wrapped: Element = { type: "element", tagName: "p", properties: {}, children: [child] }
        return wrapped
      }
      return child
    })
  }
}
