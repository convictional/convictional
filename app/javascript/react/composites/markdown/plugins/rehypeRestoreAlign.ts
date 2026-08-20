import type { Element, Root } from "hast"
import { visit } from "unist-util-visit"

// react-markdown's internal hast-util-to-jsx-runtime rewrites `align` to
// `style.textAlign`, which would defeat the [data-align] selectors in
// markdown-content.css. Move the value onto `data-align` (deleting the
// original `align` property) so CSS keeps owning text-alignment for both
// server and React surfaces — leaving `align` in place would let jsx-runtime
// emit an inline `style="text-align:..."` that wins over the selector.
export function rehypeRestoreAlign() {
  return (tree: Root) => {
    visit(tree, "element", (node: Element) => {
      if (node.tagName !== "td" && node.tagName !== "th") return
      const align = node.properties?.align
      if (typeof align === "string" && (align === "left" || align === "center" || align === "right")) {
        if (!node.properties) node.properties = {}
        node.properties["data-align"] = align
        delete node.properties.align
      }
    })
  }
}
