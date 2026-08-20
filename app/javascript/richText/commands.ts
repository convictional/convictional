import { setBlockType, toggleMark } from "prosemirror-commands"
import { Fragment, Node } from "prosemirror-model"
import { Command, TextSelection } from "prosemirror-state"

import { schema } from "./schema"

function hasInlineNonTextChild(node: Node): boolean {
  for (let i = 0; i < node.childCount; i++) {
    const child = node.child(i)
    if (child.isInline && !child.isText) return true
  }
  return false
}

// A text run is the ordered text nodes between inline non-text nodes. Collapse newlines to spaces
// (heading is a single line), trim whitespace at the run's edges, and drop nodes that trim to empty —
// ProseMirror throws on empty text nodes. Returns null when nothing survives.
function headingFromTextRun(run: Node[], level: 1 | 2 | 3): Node | null {
  const normalized = run
    .map(node => ({ text: node.text!.replace(/[\n\r]/g, " "), marks: node.marks }))
    .filter(entry => entry.text.length > 0)
  if (normalized.length === 0) return null
  normalized[0].text = normalized[0].text.replace(/^\s+/, "")
  normalized[normalized.length - 1].text = normalized[normalized.length - 1].text.replace(/\s+$/, "")
  const textNodes = normalized
    .filter(entry => entry.text.length > 0)
    .map(entry => schema.text(entry.text, entry.marks))
  if (textNodes.length === 0) return null
  return schema.nodes.heading.create({ level }, textNodes)
}

export function toggleHeading(level: 1 | 2 | 3): Command {
  return (state, dispatch, view) => {
    const { from, to } = state.selection
    let hasCodeBlock = false
    let allAtLevel = true
    state.doc.nodesBetween(from, to, node => {
      if (!node.isBlock) return
      if (node.type === schema.nodes.code_block) hasCodeBlock = true
      if (node.type !== schema.nodes.heading || node.attrs.level !== level) allAtLevel = false
    })
    if (hasCodeBlock) return false
    if (allAtLevel) return setBlockType(schema.nodes.paragraph)(state, dispatch, view)

    const targets: Array<{ node: Node; pos: number }> = []
    state.doc.nodesBetween(from, to, (node, pos) => {
      if (node.isTextblock) targets.push({ node, pos })
    })

    // Fast path: heading's content spec is `text*`, so setBlockType's clearIncompatible pass would
    // delete inline non-text nodes (e.g. images). Only reconstruct blocks that actually contain them.
    if (!targets.some(({ node }) => hasInlineNonTextChild(node))) {
      return setBlockType(schema.nodes.heading, { level })(state, dispatch, view)
    }

    const tr = state.tr
    for (const { node, pos } of [...targets].reverse()) {
      // Containers like table cells (content `paragraph`) or list items (first child must be a
      // paragraph) can't hold a heading. Skip the block rather than let ProseMirror lift or pad
      // the result, which would corrupt the doc or drop the inline image. Non-lossy: text stays.
      const $pos = state.doc.resolve(pos)
      const parent = $pos.parent
      const index = $pos.index()
      if (!hasInlineNonTextChild(node)) {
        if (parent.canReplaceWith(index, index + 1, schema.nodes.heading)) {
          tr.setBlockType(pos, pos + node.nodeSize, schema.nodes.heading, { level })
        }
        continue
      }
      const blocks: Node[] = []
      let run: Node[] = []
      const flush = () => {
        const heading = headingFromTextRun(run, level)
        if (heading) blocks.push(heading)
        run = []
      }
      node.content.forEach(child => {
        if (child.isText) {
          run.push(child)
        } else {
          flush()
          blocks.push(schema.nodes.paragraph.create(null, child))
        }
      })
      flush()
      if (parent.canReplace(index, index + 1, Fragment.from(blocks))) {
        tr.replaceWith(pos, pos + node.nodeSize, blocks)
      }
    }

    if (!dispatch) return true
    if (tr.steps.length === 0) return false
    tr.setSelection(TextSelection.near(tr.doc.resolve(tr.mapping.map(from))))
    dispatch(tr)
    return true
  }
}

export function toggleCode(): Command {
  return (state, dispatch) => {
    const textblocks: Array<{ node: Node; pos: number }> = []
    state.doc.nodesBetween(state.selection.from, state.selection.to, (node, pos) => {
      if (node.isTextblock) textblocks.push({ node, pos })
    })

    // Toggle off when every selected textblock is already a code_block — covers both the single-block
    // case (cursor inside one code_block) and the multi-block case (selection spans several code_blocks).
    const allCodeBlocks =
      textblocks.length > 0 && textblocks.every(({ node }) => node.type === schema.nodes.code_block)
    if (allCodeBlocks) {
      const range = state.selection.$from.blockRange(state.selection.$to)
      if (!range) return false
      const paragraphs = textblocks.flatMap(({ node }) =>
        node.textContent.split("\n").map(line => schema.nodes.paragraph.create({}, line ? schema.text(line) : null))
      )
      const tr = state.tr.replaceWith(range.start, range.end, paragraphs)
      tr.setSelection(TextSelection.near(tr.doc.resolve(range.start + 1)))
      if (dispatch) dispatch(tr)
      return true
    }

    if (textblocks.length <= 1) {
      return toggleMark(schema.marks.code)(state, dispatch)
    }

    const { $from, $to } = state.selection
    const range = $from.blockRange($to)
    // blockRange returns null for degenerate cross-depth selections (e.g. CellSelection); bail cleanly
    if (!range) return false

    // textContent intentionally drops inline marks — code_block schema is `content: "text*"` and disallows them.
    const text = textblocks.map(({ node }) => node.textContent).join("\n")
    const codeBlock = schema.nodes.code_block.create({}, text ? schema.text(text) : null)
    const tr = state.tr.replaceRangeWith(range.start, range.end, codeBlock)
    tr.setSelection(TextSelection.near(tr.doc.resolve(tr.mapping.map(range.start, -1) + 1)))
    if (dispatch) dispatch(tr)
    return true
  }
}
