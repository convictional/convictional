import type { Node, Parent, Root, Text } from "mdast"
import remarkParse from "remark-parse"
import { unified } from "unified"

import { REMARK_PLUGINS } from "./plugins"

// REMARK_PLUGINS includes remarkMentions, which rewrites `@[Name]` into a text
// node carrying `data.hName === "span"` and a `mention` class. We tag those
// segments so callers can re-emit them as styled spans instead of leaking the
// raw bracket syntax (or flattening to plain `@Name`).
const PROCESSOR = unified().use(remarkParse).use(REMARK_PLUGINS)

// We can't use mdast-util-to-string: it concatenates without separators, so a
// blockquote of two paragraphs becomes "helloworld" and a table row becomes
// "123". This walker inserts "\n\n" between block siblings so a collapsed
// single-line preview stays readable.
const BLOCK_TYPES = new Set([
  "paragraph",
  "heading",
  "blockquote",
  "code",
  "list",
  "listItem",
  "table",
  "tableRow",
  "tableCell",
  "thematicBreak",
])

export interface Segment {
  value: string
  isMention: boolean
}

function isParent(node: Node): node is Parent {
  return "children" in node && Array.isArray((node as Parent).children)
}

function isMentionNode(node: Text): boolean {
  const data = node.data as { hName?: string; hProperties?: { className?: unknown } } | undefined
  if (data?.hName !== "span") return false
  const className = data.hProperties?.className
  return Array.isArray(className) && className.includes("mention")
}

function collectSegments(node: Node): Segment[] {
  if (node.type === "text" || node.type === "inlineCode" || node.type === "code") {
    const value = (node as { value?: string }).value ?? ""
    if (!value) return []
    return [{ value, isMention: node.type === "text" && isMentionNode(node as Text) }]
  }
  if (node.type === "break") return [{ value: "\n", isMention: false }]
  if (node.type === "image") {
    // Parity with lib/markdown.py:_substitute_image
    const alt = ((node as { alt?: string | null }).alt ?? "").trim()
    return [{ value: alt ? `[${alt}]` : "[image]", isMention: false }]
  }
  if (!isParent(node)) return []
  const result: Segment[] = []
  for (const child of node.children) {
    const part = collectSegments(child)
    if (part.length === 0) continue
    if (result.length > 0 && BLOCK_TYPES.has(child.type)) {
      result.push({ value: "\n\n", isMention: false })
    }
    result.push(...part)
  }
  return result
}

// Flatten a markdown string into block-aware text segments. Mention segments are
// tagged so callers can style them; everything else is plain text.
export function markdownToSegments(source: string): Segment[] {
  if (!source) return []
  const tree = PROCESSOR.runSync(PROCESSOR.parse(source)) as Root
  return collectSegments(tree)
}
