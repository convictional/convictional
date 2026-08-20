import type { Node } from "prosemirror-model"
import type { EditorState } from "prosemirror-state"

export type CommentRange = { from: number; to: number; text: string }

export function getRange(state: EditorState, savedSelection: { from: number; to: number }): CommentRange | null {
  let { from, to } = state.selection

  if (from === to && savedSelection.from !== savedSelection.to) {
    from = savedSelection.from
    to = savedSelection.to
  }

  if (from === to) {
    const $pos = state.doc.resolve(from)
    // Guard against cursor resolving into a non-textblock parent
    if (!$pos.parent.isTextblock) return null
    from = $pos.start()
    to = $pos.start() + $pos.parent.content.size
    if (from === to) return null
  }

  const text = state.doc.textBetween(from, to).trim()
  if (text) return { from, to, text }

  const holder: { node: Node | null } = { node: null }
  state.doc.nodesBetween(from, to, node => {
    if (holder.node) return false
    if (node.type.name === "image") {
      holder.node = node
      return false
    }
    return true
  })

  const found = holder.node
  if (found) {
    const alt = typeof found.attrs.alt === "string" ? found.attrs.alt.trim() : ""
    const title = typeof found.attrs.title === "string" ? found.attrs.title.trim() : ""
    const label = alt || title || "Image"
    return { from, to, text: label }
  }

  return null
}
