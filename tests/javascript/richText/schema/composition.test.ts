import { expect, test } from "vitest"
import { builders } from "prosemirror-test-builder"
import { EditorState, Plugin, Transaction } from "prosemirror-state"

import { plugins as schemaPlugins, schema } from "../../../../app/javascript/richText/schema"
import { getKeymap } from "../../../../app/javascript/richText/schema/keymap"
import { selFor } from "./testHelpers"

const { doc, paragraph, table, table_row, table_cell, table_header } = builders(schema)

// Mirrors the plugin composition in react/editor/Editor.tsx (minus react-prosemirror
// and feature-level plugins, which are not relevant to keymap ordering). The
// invariant under test: getKeymap() runs before schemaPlugins so ArrowUp/Down
// boundary-exit commands get first crack before tableEditing() claims arrow keys.
function composedPlugins(): Plugin[] {
  return [getKeymap(), ...schemaPlugins]
}

// Simulates ProseMirror's plugin-ordered handleKeyDown dispatch.
// Returns the dispatched transaction, or null if no plugin handled the event.
function dispatchKey(state: EditorState, plugins: Plugin[], key: string): Transaction | null {
  let dispatched: Transaction | null = null
  const dispatch = (tr: Transaction) => {
    dispatched = tr
  }
  for (const plugin of plugins) {
    const handler = plugin.props?.handleKeyDown
    if (!handler) continue
    // @handlewithcare/react-prosemirror's EditorView is complex to mock;
    // plugin handlers read view.state and view.dispatch, which is enough.
    const view = { state, dispatch } as any
    const event = { key, shiftKey: false, preventDefault: () => {}, stopPropagation: () => {} } as any
    if (handler(view, event)) return dispatched
  }
  return null
}

test("ArrowDown at last-cell boundary exits the table via getKeymap, not tableEditing", () => {
  // Single-row, single-cell table — caret at end of the only cell.
  const input = doc(table(table_row(table_cell(paragraph("x<a>")))))
  const state = EditorState.create({ schema, doc: input, selection: selFor(input), plugins: composedPlugins() })
  const tr = dispatchKey(state, state.plugins, "ArrowDown")

  expect(tr).not.toBeNull()
  // Expected: original table preserved, new paragraph appended, caret inside it.
  const expected = doc(table(table_row(table_cell(paragraph("x")))), paragraph(""))
  expect(tr!.doc.eq(expected)).toBe(true)
})

test("ArrowUp at first-cell boundary exits the table via getKeymap, not tableEditing", () => {
  const input = doc(table(table_row(table_header(paragraph("<a>x")))))
  const state = EditorState.create({ schema, doc: input, selection: selFor(input), plugins: composedPlugins() })
  const tr = dispatchKey(state, state.plugins, "ArrowUp")

  expect(tr).not.toBeNull()
  const expected = doc(paragraph(""), table(table_row(table_header(paragraph("x")))))
  expect(tr!.doc.eq(expected)).toBe(true)
})
