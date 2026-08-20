import { useEditorEventCallback, useEditorState } from "@handlewithcare/react-prosemirror"
import { MarkType, NodeType } from "prosemirror-model"
import { Command, EditorState, Selection } from "prosemirror-state"
import { isInTable, selectedRect } from "prosemirror-tables"
import { useEffect, useRef } from "react"

import { schema } from "~/richText/schema"

export interface EditorActions {
  runCmd: (cmd: Command) => void
  canRunCmd: (cmd: Command) => boolean
  applyLink: (href: string) => void
  insertImage: (src: string, alt: string) => void
  insertTable: () => void
  isMarkActive: (type: MarkType) => boolean
  getHeadingLevel: () => number | undefined
  hasAncestorOfType: (type: NodeType) => boolean
  canDeleteRow: () => boolean
  canDeleteColumn: () => boolean
  lastSelectionRef: React.RefObject<{ from: number; to: number; text: string }>
}

function isMarkActiveInState(state: EditorState, type: MarkType): boolean {
  const { from, $from, to, empty } = state.selection
  if (empty) return !!type.isInSet(state.storedMarks || $from.marks())
  return state.doc.rangeHasMark(from, to, type)
}

// Must be called inside <Editor> children (requires ProseMirror context).
// Provides general-purpose editor operations for any UI component.
export function useEditorActions(): EditorActions {
  const state = useEditorState()

  // Track the last non-empty selection so actions work correctly when the
  // triggering UI (toolbar, floating menu, etc.) steals focus from the editor.
  const lastSelectionRef = useRef<{ from: number; to: number; text: string }>({ from: 0, to: 0, text: "" })
  useEffect(() => {
    if (!state.selection.empty) {
      const { from, to } = state.selection
      lastSelectionRef.current = { from, to, text: state.doc.textBetween(from, to) }
    }
  }, [state])

  const runCmd = useEditorEventCallback((view, cmd: Command) => {
    cmd(view.state, view.dispatch, view)
    view.focus()
  })

  const canRunCmd = useEditorEventCallback((view, cmd: Command) => {
    return cmd(view.state, undefined, view)
  })

  const applyLink = useEditorEventCallback((view, href: string) => {
    const sel = lastSelectionRef.current
    if (!href || sel.from === sel.to) return
    if (!/^https?:\/\//i.test(href)) return

    const tr = view.state.tr
    tr.addMark(sel.from, sel.to, schema.marks.link.create({ href }))
    tr.setSelection(Selection.near(tr.doc.resolve(sel.to)))
    view.dispatch(tr)
    view.focus()
  })

  const insertImage = useEditorEventCallback((view, src: string, alt: string) => {
    if (!src || !/^https?:\/\//i.test(src)) return

    const imageNode = schema.nodes.image.create({ src, alt })
    const tr = view.state.tr.replaceSelectionWith(imageNode)
    view.dispatch(tr)
    view.focus()
  })

  const insertTable = useEditorEventCallback(view => {
    const nodes = schema.nodes
    const row = (type: NodeType, n: number) =>
      nodes.table_row.create(
        null,
        Array.from({ length: n }, () => type.createAndFill()!)
      )
    const tableNode = nodes.table.create(null, [
      row(nodes.table_header, 3),
      row(nodes.table_cell, 3),
      row(nodes.table_cell, 3),
    ])
    const { from } = view.state.selection
    const tr = view.state.tr.replaceSelectionWith(tableNode)
    // The inserted table opens at the pre-transaction `from`; step three
    // tokens deeper (table, row, cell) to land in the first header cell.
    // We intentionally do NOT use `tr.mapping.map(from)` — when
    // replaceSelectionWith replaces a containing empty block, the mapping's
    // default forward bias pushes the position past the inserted table.
    tr.setSelection(Selection.near(tr.doc.resolve(from + 3)))
    view.dispatch(tr)
    view.focus()
  })

  const isMarkActive = (type: MarkType): boolean => isMarkActiveInState(state, type)

  const getHeadingLevel = (): number | undefined => {
    const { $from } = state.selection
    if ($from.node().type === schema.nodes.heading) {
      return $from.node().attrs.level as number
    }
    return undefined
  }

  // ProseMirror wraps blockquote content in paragraphs — $from.parent is the
  // paragraph, not the blockquote — so a simple parent check isn't enough.
  const hasAncestorOfType = (type: NodeType): boolean => {
    const { $from } = state.selection
    for (let depth = $from.depth; depth > 0; depth--) {
      if ($from.node(depth).type === type) return true
    }
    return false
  }

  // prosemirror-tables' deleteRow/deleteColumn return true whenever
  // isInTable(state), but their "would remove the entire table" guard only
  // runs when dispatch is passed. We replicate the guard so 1-row / 1-column
  // tables disable the button instead of showing it as enabled-but-no-op.
  const canDeleteRow = (): boolean => {
    if (!isInTable(state)) return false
    const rect = selectedRect(state)
    return !(rect.top === 0 && rect.bottom === rect.map.height)
  }
  const canDeleteColumn = (): boolean => {
    if (!isInTable(state)) return false
    const rect = selectedRect(state)
    return !(rect.left === 0 && rect.right === rect.map.width)
  }

  return {
    runCmd,
    canRunCmd,
    applyLink,
    insertImage,
    insertTable,
    isMarkActive,
    getHeadingLevel,
    hasAncestorOfType,
    canDeleteRow,
    canDeleteColumn,
    lastSelectionRef,
  }
}
