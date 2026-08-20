import { Node } from "prosemirror-model"
import { EditorState } from "prosemirror-state"
import { builders } from "prosemirror-test-builder"
import { EditorView } from "prosemirror-view"
import { afterEach, describe, expect, test } from "vitest"
import { prosemirrorToYXmlFragment, ySyncPlugin, ySyncPluginKey } from "y-prosemirror"
import * as Y from "yjs"

import {
  collapsibleHeadingsPlugin,
  collapsibleHeadingsPluginKey,
} from "../../../../../app/javascript/react/composites/editor/features/collapsibleHeadings"
import { schema, serialize } from "../../../../../app/javascript/richText/schema"

const { doc, heading, paragraph } = builders(schema)

function mountView(document_: Node) {
  const mount = document.createElement("div")
  document.body.appendChild(mount)
  const view = new EditorView(mount, {
    state: EditorState.create({ schema, doc: document_, plugins: [collapsibleHeadingsPlugin] }),
  })
  return { view, mount }
}

// A Yjs-bound editor: seed the ProseMirror content into the shared yXmlFragment and
// mount with ySyncPlugin in front of the collapsible-headings plugin, exactly as the
// production editor does (useCollaboration). This is what activates the plugin's
// relative-position anchor path (makeAnchor stores a Yjs RelativePosition, resolveAnchor
// goes through relativePositionToAbsolutePosition) instead of the plain absolute fallback.
function mountYjsView(document_: Node) {
  const ydoc = new Y.Doc()
  const yXmlFragment = ydoc.getXmlFragment("prosemirror")
  prosemirrorToYXmlFragment(document_, yXmlFragment)

  const mount = document.createElement("div")
  document.body.appendChild(mount)
  // No doc option: ySyncPlugin's _forceRerender projects yXmlFragment into the view at
  // construction and builds the binding whose mapping the relative path depends on.
  const view = new EditorView(mount, {
    state: EditorState.create({ schema, plugins: [ySyncPlugin(yXmlFragment), collapsibleHeadingsPlugin] }),
  })
  return { ydoc, yXmlFragment, view, mount }
}

// A peer Y.Doc synced from the editor's doc; edits made on it and applied back arrive as
// remote-origin updates, which y-prosemirror replays as a replace-all transaction.
function syncedPeer(ydoc: Y.Doc) {
  const peer = new Y.Doc()
  Y.applyUpdate(peer, Y.encodeStateAsUpdate(ydoc))
  return { peer, fragment: peer.getXmlFragment("prosemirror") }
}

function applyPeerUpdate(ydoc: Y.Doc, peer: Y.Doc) {
  Y.applyUpdate(ydoc, Y.encodeStateAsUpdate(peer, Y.encodeStateVector(ydoc)))
}

// The toggle meta expects the position immediately before the heading node, i.e. the
// offset such that doc.nodeAt(offset) is the heading. doc.forEach hands back exactly
// that offset for each top-level child.
function headingStartByText(document_: Node, text: string): number {
  let found: number | null = null
  document_.forEach((node, offset) => {
    if (node.type.name === "heading" && node.textContent === text) found = offset
  })
  if (found === null) throw new Error(`no heading with text: ${text}`)
  return found
}

function headingNodeAt(document_: Node, start: number): Node {
  const node = document_.nodeAt(start)
  if (!node) throw new Error(`no node at ${start}`)
  return node
}

function toggle(view: EditorView, pos: number) {
  view.dispatch(view.state.tr.setMeta(collapsibleHeadingsPluginKey, { toggle: pos }))
}

function collapsedCount(mount: HTMLElement) {
  return mount.querySelectorAll(".heading-section-collapsed").length
}

function toggleButtons(mount: HTMLElement) {
  return mount.querySelectorAll<HTMLButtonElement>("button.heading-collapse-toggle")
}

describe("collapsibleHeadings", () => {
  let cleanupView: (() => void) | null = null

  afterEach(() => {
    cleanupView?.()
    cleanupView = null
  })

  test("renders a chevron toggle for every heading level, and is a no-op without headings", () => {
    const withHeadings = mountView(
      doc(heading({ level: 1 }, "H1"), paragraph("under h1"), heading({ level: 2 }, "H2"), heading({ level: 3 }, "H3"))
    )
    cleanupView = () => withHeadings.view.destroy()
    expect(toggleButtons(withHeadings.mount).length).toBe(3)
    expect(collapsedCount(withHeadings.mount)).toBe(0)
    withHeadings.view.destroy()

    const noHeadings = mountView(doc(paragraph("just text"), paragraph("and more")))
    cleanupView = () => noHeadings.view.destroy()
    expect(toggleButtons(noHeadings.mount).length).toBe(0)
    expect(collapsedCount(noHeadings.mount)).toBe(0)
  })

  test("chevron aria-expanded reflects collapse state and clicking it toggles", () => {
    const { view, mount } = mountView(
      doc(heading({ level: 2 }, "Section"), paragraph("body one"), paragraph("body two"))
    )
    cleanupView = () => view.destroy()

    const button = toggleButtons(mount)[0]
    expect(button.getAttribute("aria-expanded")).toBe("true")

    button.click()
    expect(toggleButtons(mount)[0].getAttribute("aria-expanded")).toBe("false")
    expect(collapsedCount(mount)).toBe(2)

    toggleButtons(mount)[0].click()
    expect(toggleButtons(mount)[0].getAttribute("aria-expanded")).toBe("true")
    expect(collapsedCount(mount)).toBe(0)
  })

  test("collapse scopes the section to the next same-or-higher-level heading", () => {
    const document_ = doc(
      paragraph("intro"), // before the H2 — never hidden
      heading({ level: 1 }, "Top"),
      paragraph("top body"), // belongs to H1, before the H2 — never hidden
      heading({ level: 2 }, "Middle"),
      paragraph("middle body"), // hidden by Middle
      heading({ level: 3 }, "Deep"), // hidden by Middle (nested lower level)
      paragraph("deep body"), // hidden by Middle
      heading({ level: 2 }, "Sibling"), // stops Middle's section — not hidden
      paragraph("sibling body"), // after — never hidden
      heading({ level: 1 }, "TopTwo"),
      paragraph("end")
    )
    const { view, mount } = mountView(document_)
    cleanupView = () => view.destroy()

    // Collapsing the H2 hides exactly its 3 following blocks up to the next H2 — the
    // nested H3 and its content included, nothing before the H2 or at/after the sibling.
    toggle(view, headingStartByText(view.state.doc, "Middle"))
    expect(collapsedCount(mount)).toBe(3)

    // Collapsing the first H1 instead hides everything down to the next H1: its body,
    // both subheadings, and all their content (7 blocks) — the nested sections too.
    toggle(view, headingStartByText(view.state.doc, "Middle")) // re-expand Middle first
    toggle(view, headingStartByText(view.state.doc, "Top"))
    expect(collapsedCount(mount)).toBe(7)
  })

  test("re-toggling fully re-expands, and an independently collapsed subheading survives", () => {
    const document_ = doc(
      heading({ level: 1 }, "Parent"),
      paragraph("parent body"),
      heading({ level: 2 }, "Child"),
      paragraph("child body"),
      paragraph("child more"),
      heading({ level: 1 }, "ParentTwo"),
      paragraph("end")
    )
    const { view, mount } = mountView(document_)
    cleanupView = () => view.destroy()

    // Collapse the child H2 on its own: hides its 2 blocks.
    toggle(view, headingStartByText(view.state.doc, "Child"))
    expect(collapsedCount(mount)).toBe(2)

    // Collapse the parent H1 on top: hides parent body, the Child heading, and both
    // child blocks — 4 distinct blocks.
    toggle(view, headingStartByText(view.state.doc, "Parent"))
    expect(collapsedCount(mount)).toBe(4)

    // Re-expanding the parent removes only the parent's decorations; the child's own
    // collapse is independent and its 2 blocks stay hidden.
    toggle(view, headingStartByText(view.state.doc, "Parent"))
    expect(collapsedCount(mount)).toBe(2)

    // Re-toggling the child then removes everything it added — a full re-expand.
    toggle(view, headingStartByText(view.state.doc, "Child"))
    expect(collapsedCount(mount)).toBe(0)
  })

  test("collapsing never mutates the document", () => {
    const { view } = mountView(doc(heading({ level: 2 }, "Section"), paragraph("body one"), paragraph("body two")))
    cleanupView = () => view.destroy()

    const before = view.state.doc
    const beforeMarkdown = serialize(before)

    toggle(view, headingStartByText(view.state.doc, "Section"))

    // Collapse is decoration-only: same serialized markdown and structurally equal doc.
    expect(serialize(view.state.doc)).toBe(beforeMarkdown)
    expect(view.state.doc.eq(before)).toBe(true)
  })

  test("collapse survives an edit before the heading and clears when the heading is deleted", () => {
    const { view, mount } = mountView(
      doc(
        paragraph("intro"),
        heading({ level: 2 }, "Section"),
        paragraph("body one"),
        paragraph("body two"),
        heading({ level: 2 }, "Next"),
        paragraph("end")
      )
    )
    cleanupView = () => view.destroy()

    // Collapse first, then deliver an insertion strictly before the heading as a live
    // event. The collapse tracks the heading through the edit's mapping and the same
    // two blocks stay hidden.
    toggle(view, headingStartByText(view.state.doc, "Section"))
    expect(collapsedCount(mount)).toBe(2)
    view.dispatch(view.state.tr.insert(1, schema.text("PREFIX")))
    expect(collapsedCount(mount)).toBe(2)

    // Deleting the collapsed heading node leaves no dangling collapsed decorations.
    const start = headingStartByText(view.state.doc, "Section")
    const headingNode = headingNodeAt(view.state.doc, start)
    view.dispatch(view.state.tr.delete(start, start + headingNode.nodeSize))
    expect(collapsedCount(mount)).toBe(0)

    // The stale anchor is pruned, not merely skipped: an unrelated later edit keeps it
    // gone rather than re-remapping a dead entry forever.
    view.dispatch(view.state.tr.insert(1, schema.text("MORE")))
    expect(collapsedCount(mount)).toBe(0)
    expect(collapsibleHeadingsPluginKey.getState(view.state)?.collapsed.length).toBe(0)
  })

  test("collapse survives a remote replace-all via the Yjs relative-position anchor", () => {
    const { ydoc, view, mount } = mountYjsView(
      doc(
        heading({ level: 2 }, "Section"),
        paragraph("body one"),
        paragraph("body two"),
        heading({ level: 2 }, "Next"),
        paragraph("end")
      )
    )
    cleanupView = () => view.destroy()

    // Prove the relative path is live, not the fallback: ySyncPlugin must expose a real
    // binding with a populated Yjs↔PM mapping. resolveAnchor only uses relative positions
    // when mapping.size > 0, so a non-empty mapping is what routes us off the fallback.
    const ystate = ySyncPluginKey.getState(view.state)
    expect(ystate?.binding).toBeTruthy()
    expect(ystate.binding.mapping.size).toBeGreaterThan(0)

    // Collapse "Section" — hides "body one" and "body two".
    toggle(view, headingStartByText(view.state.doc, "Section"))
    expect(collapsedCount(mount)).toBe(2)
    expect(toggleButtons(mount)[0].getAttribute("aria-expanded")).toBe("false")

    // A collaborator inserts a new paragraph at the very top, then that update lands
    // AFTER the collapse. y-prosemirror replays it as a replace-all whose mapping would
    // collapse a plainly-mapped absolute position onto the wrong node — only the Yjs
    // relative anchor still resolves to the shifted heading.
    const { peer, fragment } = syncedPeer(ydoc)
    Y.transact(peer, () => {
      const para = new Y.XmlElement("paragraph")
      const text = new Y.XmlText()
      text.insert(0, "REMOTE")
      para.insert(0, [text])
      fragment.insert(0, [para])
    })
    applyPeerUpdate(ydoc, peer)

    // The heading moved, but the same two blocks stay hidden and its chevron stays folded.
    expect(view.state.doc.textContent.startsWith("REMOTE")).toBe(true)
    expect(collapsedCount(mount)).toBe(2)
    expect(toggleButtons(mount)[0].getAttribute("aria-expanded")).toBe("false")
  })

  test("remote deletion of the collapsed heading clears its decorations (Yjs)", () => {
    const { ydoc, view, mount } = mountYjsView(
      doc(
        heading({ level: 2 }, "Section"),
        paragraph("body one"),
        paragraph("body two"),
        heading({ level: 2 }, "Next"),
        paragraph("end")
      )
    )
    cleanupView = () => view.destroy()

    toggle(view, headingStartByText(view.state.doc, "Section"))
    expect(collapsedCount(mount)).toBe(2)

    // A collaborator deletes the collapsed heading block. Its relative anchor no longer
    // resolves to a heading node, so the section decorations are pruned rather than left
    // dangling over the now-headingless blocks.
    const { peer, fragment } = syncedPeer(ydoc)
    Y.transact(peer, () => fragment.delete(0, 1))
    applyPeerUpdate(ydoc, peer)

    expect(collapsedCount(mount)).toBe(0)
  })
})
