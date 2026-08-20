import { test, expect } from "vitest"
import { joinBackward } from "prosemirror-commands"
import { keydownHandler } from "prosemirror-keymap"
import { builders } from "prosemirror-test-builder"
import { Command, EditorState, Plugin, TextSelection, Transaction } from "prosemirror-state"
import { EditorView } from "prosemirror-view"

import { convertTaskItemToParaBackspace } from "../../../app/javascript/richText/schema/keymap"
import { pmu, schema } from "../../../app/javascript/richText/schema/instance"

const { doc, paragraph, bullet_list, task_list_item } = builders(schema)

// For doc(bullet_list(task_list_item(paragraph("a"), paragraph("b")))) with the
// cursor at the start of p("b"), the upstream Backspace handler computes
// replaceRangeWith($from.before() - 2, $from.before() + task_list_item.nodeSize, ...)
// = replaceRangeWith(3, 13, ...) — but doc.content.size is 10, so resolving 13
// throws "Position 13 out of range" (Sentry DECIDE-8GD).
test("Backspace at start of non-first paragraph in a task_list_item does not throw", () => {
  const state = stateWithCursorAtStartOfParagraph(
    doc(bullet_list(task_list_item({ checked: false }, paragraph("a"), paragraph("b")))),
    "b"
  )

  expect(() => libBackspaceCommand()(state, () => {})).not.toThrow()
})

// Documents the behavior our `Backspace: () => false` override is delegating to
// when the cursor is at the start of the first paragraph in the first task item.
test("convertTaskItemToParaBackspace lifts a single task_list_item out of its bullet_list", () => {
  const state = stateWithCursorAtStartOfParagraph(
    doc(bullet_list(task_list_item({ checked: false }, paragraph("checkbox content")))),
    "checkbox content"
  )

  const tr = applyCommand(state, convertTaskItemToParaBackspace)
  expect(tr).not.toBeNull()
  expect(tr!.doc.toJSON()).toEqual(doc(paragraph("checkbox content")).toJSON())
})

// Documents the behavior our `Backspace: () => false` override is delegating to
// when the cursor is at the start of a non-first paragraph: default Backspace's
// joinBackward merges the paragraph into its predecessor inside the same item.
test("joinBackward merges a non-first paragraph into the previous one inside the same task_list_item", () => {
  const state = stateWithCursorAtStartOfParagraph(
    doc(bullet_list(task_list_item({ checked: false }, paragraph("a"), paragraph("b")))),
    "b"
  )

  const tr = applyCommand(state, joinBackward)
  expect(tr).not.toBeNull()
  expect(tr!.doc.toJSON()).toEqual(
    doc(bullet_list(task_list_item({ checked: false }, paragraph("ab")))).toJSON()
  )
})

function stateWithCursorAtStartOfParagraph(d: ReturnType<typeof doc>, text: string): EditorState {
  const pBefore = positionBeforeParagraph(d, text)
  return EditorState.create({ doc: d, selection: TextSelection.create(d, pBefore + 1) })
}

function applyCommand(state: EditorState, command: Command): Transaction | null {
  let captured: Transaction | null = null
  command(state, tr => {
    captured = tr
  })
  return captured
}

// Pulls the Backspace handler from prosemirror-keymap's plugin via plugin.props.handleKeyDown.
// That's an implementation detail of prosemirror-keymap rather than its public API; if a
// future version stops registering the handler under that name the guard below trips.
function libBackspaceCommand(): Command {
  const plugin = pmu.keymapPlugin() as Plugin
  const handleKeyDown = (plugin.props as { handleKeyDown?: ReturnType<typeof keydownHandler> }).handleKeyDown
  if (!handleKeyDown) throw new Error("pmu.keymapPlugin() did not register handleKeyDown")

  return (state, dispatch, view) => {
    let dispatched = false
    // TaskListItemExtension.isAtStart needs view.endOfTextblock("backward") to
    // return true to advance into the buggy code path.
    const stubView = {
      state,
      dispatch: (tr: Transaction) => {
        dispatched = true
        if (dispatch) dispatch(tr)
      },
      endOfTextblock: () => true,
    } as unknown as EditorView
    const handled = handleKeyDown(view ?? stubView, new KeyboardEvent("keydown", { key: "Backspace" }))
    return handled || dispatched
  }
}

function positionBeforeParagraph(d: ReturnType<typeof doc>, text: string): number {
  let result = -1
  d.descendants((node, pos) => {
    if (result !== -1) return false
    if (node.type === schema.nodes.paragraph && node.textContent === text) {
      result = pos
      return false
    }
    return true
  })
  if (result === -1) throw new Error(`paragraph with text "${text}" not found`)
  return result
}
