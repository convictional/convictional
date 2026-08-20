import type { PhrasingContent, Root, Text } from "mdast"
import type { Plugin } from "unified"
import { visit } from "unist-util-visit"

// Mirrors MENTION_PATTERN in app/models/collaboration/workspace.py:1033
// (the `g` flag is the only difference, for `matchAll`).
const MENTION_PATTERN = /@\[([^\]]+)\]/g

function buildMentionNode(name: string): Text {
  return {
    type: "text",
    value: `@${name}`,
    data: {
      hName: "span",
      hProperties: {
        className: ["mention"],
        "data-name": name,
      },
    },
  }
}

export const remarkMentions: Plugin<[], Root> = () => {
  return tree => {
    visit(tree, "text", (node: Text, index, parent) => {
      if (!parent || index === undefined) return
      const value = node.value
      const replacements: PhrasingContent[] = []
      let cursor = 0
      for (const match of value.matchAll(MENTION_PATTERN)) {
        const [whole, name] = match
        const start = match.index
        if (start > cursor) {
          replacements.push({ type: "text", value: value.slice(cursor, start) })
        }
        replacements.push(buildMentionNode(name))
        cursor = start + whole.length
      }
      if (replacements.length === 0) return
      if (cursor < value.length) {
        replacements.push({ type: "text", value: value.slice(cursor) })
      }
      const parentChildren = (parent as { children: PhrasingContent[] }).children
      parentChildren.splice(index, 1, ...replacements)
      return index + replacements.length
    })
  }
}
