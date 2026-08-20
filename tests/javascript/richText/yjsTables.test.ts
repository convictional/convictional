import { expect, test } from "vitest"
import { builders } from "prosemirror-test-builder"
import { prosemirrorToYXmlFragment, yXmlFragmentToProseMirrorRootNode } from "y-prosemirror"
import * as Y from "yjs"

import { schema } from "../../../app/javascript/richText/schema"

const { doc, paragraph, table, table_row, table_cell, table_header } = builders(schema)

// Yjs sync is node-type agnostic — it syncs the XML fragment representation.
// These tests cover the two paths that matter for collab:
// (1) PM doc ↔ Yjs XmlFragment round-trip (local serialization).
// (2) One-way replication via encodeStateAsUpdate/applyUpdate — the happy-path
//     sync. True concurrent-edit convergence (both docs edit in parallel, then
//     exchange updates bidirectionally) is NOT covered here.

test("ProseMirror table round-trips through a Yjs XmlFragment", () => {
  const original = doc(
    table(
      table_row(table_header(paragraph("Name")), table_header(paragraph("Role"))),
      table_row(table_cell(paragraph("Alice")), table_cell(paragraph("Dev")))
    )
  )

  const ydoc = new Y.Doc()
  const fragment = ydoc.getXmlFragment("prosemirror")
  prosemirrorToYXmlFragment(original, fragment)

  const roundTripped = yXmlFragmentToProseMirrorRootNode(fragment, schema)
  expect(roundTripped.eq(original)).toBe(true)
})

test("docB replicates docA's table via an update message", () => {
  // Simulates the seed-then-sync path: docA creates a table, docB receives the
  // update and reconstructs the same ProseMirror doc. Does NOT exercise the CRDT
  // merge path (that requires concurrent edits on both sides with bidirectional update exchange).
  const docA = new Y.Doc()
  const docB = new Y.Doc()
  const fragmentA = docA.getXmlFragment("prosemirror")
  const fragmentB = docB.getXmlFragment("prosemirror")

  const tableDoc = doc(
    table(
      table_row(table_header(paragraph("A"))),
      table_row(table_cell(paragraph("1")))
    )
  )
  prosemirrorToYXmlFragment(tableDoc, fragmentA)

  // Send A's state to B via an update message (same mechanism as the WebSocket provider).
  const update = Y.encodeStateAsUpdate(docA)
  Y.applyUpdate(docB, update)

  const recovered = yXmlFragmentToProseMirrorRootNode(fragmentB, schema)
  expect(recovered.eq(tableDoc)).toBe(true)
})
