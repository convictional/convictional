import { Node } from "prosemirror-model"
import { Command, EditorState, NodeSelection, Plugin, Selection, TextSelection, Transaction } from "prosemirror-state"
import { expect } from "vitest"

// prosemirror-test-builder attaches a `.tag` map to nodes based on `<a>`/`<b>` markers
// embedded in the builder input — hence the cast through `Node & { tag: ... }`.
export function selFor(doc: Node): Selection {
  const tagged = doc as Node & { tag: Record<string, number | undefined> }
  const a = tagged.tag.a
  if (a != null) {
    const $a = doc.resolve(a)
    if ($a.parent.inlineContent) {
      return new TextSelection($a, tagged.tag.b != null ? doc.resolve(tagged.tag.b) : undefined)
    }
    return new NodeSelection($a)
  }
  return TextSelection.atStart(doc)
}

export function mkState(doc: Node, plugins: Plugin[] = []): EditorState {
  return EditorState.create({ doc, selection: selFor(doc), plugins })
}

// Guards against the latent bug where a command returns true without dispatching —
// the `seen` flag makes that silently-passing case a test failure.
export function assertCommand(cmd: Command, doc: Node, expected: Node): void {
  const state = mkState(doc)
  let seen = false
  const handled = cmd(state, (tr: Transaction) => {
    seen = true
    expect(tr.doc.eq(expected)).toBe(true)
  })
  expect(handled).toBe(true)
  expect(seen).toBe(true)
}

export function assertNoOp(cmd: Command, doc: Node): void {
  const handled = cmd(mkState(doc), () => {
    throw new Error("command should not have dispatched")
  })
  expect(handled).toBe(false)
}
