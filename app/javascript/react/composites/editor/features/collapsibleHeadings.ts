import type { Node } from "prosemirror-model"
import { Plugin, PluginKey } from "prosemirror-state"
import { Decoration, DecorationSet, type EditorView } from "prosemirror-view"
import { absolutePositionToRelativePosition, relativePositionToAbsolutePosition, ySyncPluginKey } from "y-prosemirror"
import type { Doc, RelativePosition, XmlFragment } from "yjs"

import { schema } from "~/richText/schema"

// The class applied (via CSS display:none) to every block hidden inside a collapsed
// section. Exported so the comment gutter can detect a mark stranded in a collapsed
// section and re-anchor its marker to the heading (see markAnchorElement).
export const COLLAPSED_SECTION_CLASS = "heading-section-collapsed"

// The Yjs↔ProseMirror position map y-prosemirror threads through its helpers;
// not exported by name, so recover it from the helper signature.
type ProsemirrorMapping = Parameters<typeof absolutePositionToRelativePosition>[2]

// A collapse is a local-only view concern, never part of the document, so it must
// stay out of the shared Yjs doc: one collaborator hiding a section on their screen
// must not fold it away for everyone. The plugin dispatches only setMeta and adds
// decorations — it never mutates the doc.

interface CollapsedAnchor {
  rel: RelativePosition | null
  pos: number
}

interface CollapsibleHeadingsState {
  collapsed: CollapsedAnchor[]
  decorations: DecorationSet
}

// Minimal shape of the ySyncPlugin state we read (its key is typed as `any`).
interface YSyncState {
  doc: Doc
  type: XmlFragment
  binding: { mapping: ProsemirrorMapping } | null
  isChangeOrigin: boolean
}

interface ToggleMeta {
  toggle: number
}

export const collapsibleHeadingsPluginKey = new PluginKey<CollapsibleHeadingsState>("collapsibleHeadings")

function makeAnchor(pos: number, ystate: YSyncState | undefined): CollapsedAnchor {
  if (ystate?.binding) {
    return { rel: absolutePositionToRelativePosition(pos, ystate.type, ystate.binding.mapping), pos }
  }
  return { rel: null, pos }
}

function resolveAnchor(anchor: CollapsedAnchor, ystate: YSyncState | undefined): number | null {
  if (anchor.rel && ystate?.binding && ystate.binding.mapping.size > 0) {
    return relativePositionToAbsolutePosition(ystate.doc, ystate.type, anchor.rel, ystate.binding.mapping)
  }
  return anchor.pos
}

function buildChevron(view: EditorView, getPos: () => number | undefined, isCollapsed: boolean): HTMLElement {
  const button = document.createElement("button")
  button.type = "button"
  button.className = "heading-collapse-toggle"
  button.contentEditable = "false"
  button.setAttribute("aria-expanded", isCollapsed ? "false" : "true")
  button.setAttribute("aria-label", isCollapsed ? "Expand section" : "Collapse section")

  const icon = document.createElement("span")
  icon.className = "material-symbols-outlined"
  icon.textContent = "chevron_right"
  button.appendChild(icon)

  button.addEventListener("mousedown", event => event.preventDefault(), true)
  button.addEventListener("click", event => {
    event.preventDefault()
    event.stopPropagation()
    const pos = getPos()
    if (pos == null) return
    view.dispatch(view.state.tr.setMeta(collapsibleHeadingsPluginKey, { toggle: pos - 1 }))
  })

  return button
}

function buildDecorations(doc: Node, collapsed: CollapsedAnchor[], ystate: YSyncState | undefined): DecorationSet {
  const collapsedStarts = new Set<number>()
  for (const anchor of collapsed) {
    const pos = resolveAnchor(anchor, ystate)
    if (pos == null) continue
    if (doc.nodeAt(pos)?.type !== schema.nodes.heading) continue
    collapsedStarts.add(pos)
  }

  const children: { node: Node; offset: number }[] = []
  doc.forEach((node, offset) => children.push({ node, offset }))

  const decorations: Decoration[] = []
  for (let i = 0; i < children.length; i++) {
    const { node, offset } = children[i]
    if (node.type !== schema.nodes.heading) continue

    const isCollapsed = collapsedStarts.has(offset)
    decorations.push(
      Decoration.widget(offset + 1, (view, getPos) => buildChevron(view, getPos, isCollapsed), {
        side: -1,
        key: `heading-collapse:${offset}:${isCollapsed}`,
      })
    )

    if (!isCollapsed) continue

    const level = node.attrs.level as number
    for (let j = i + 1; j < children.length; j++) {
      const sibling = children[j]
      if (sibling.node.type === schema.nodes.heading && (sibling.node.attrs.level as number) <= level) break
      decorations.push(
        Decoration.node(sibling.offset, sibling.offset + sibling.node.nodeSize, { class: COLLAPSED_SECTION_CLASS })
      )
    }
  }

  return DecorationSet.create(doc, decorations)
}

export const collapsibleHeadingsPlugin = new Plugin<CollapsibleHeadingsState>({
  key: collapsibleHeadingsPluginKey,
  state: {
    init(_config, state) {
      const ystate = ySyncPluginKey.getState(state) as YSyncState | undefined
      return { collapsed: [], decorations: buildDecorations(state.doc, [], ystate) }
    },
    apply(tr, value, _oldState, newState) {
      const ystate = ySyncPluginKey.getState(newState) as YSyncState | undefined
      const meta = tr.getMeta(collapsibleHeadingsPluginKey) as ToggleMeta | undefined

      // Remap each anchor's absolute fallback on every transaction so it tracks local
      // edits, then rebuild decorations from the anchors unconditionally. This inverts
      // pendingCommentDecoration.ts (static fallback, conditional map-forward rebuild):
      // an unconditional rebuild is what re-validates the heading node and drops sections
      // whose heading was deleted, but it means the fallback must be remapped here or a
      // non-Yjs collapse goes stale after any local edit (Yjs relative positions cover
      // the remote replace-all).
      let collapsed = value.collapsed.map(anchor => ({ ...anchor, pos: tr.mapping.map(anchor.pos, -1) }))

      if (meta) {
        const existing = collapsed.findIndex(anchor => resolveAnchor(anchor, ystate) === meta.toggle)
        collapsed =
          existing >= 0
            ? collapsed.filter((_, index) => index !== existing)
            : [...collapsed, makeAnchor(meta.toggle, ystate)]
      }

      // Drop anchors whose heading is gone so collapsed[] can't accumulate dead entries.
      collapsed = collapsed.filter(anchor => {
        const pos = resolveAnchor(anchor, ystate)
        return pos != null && newState.doc.nodeAt(pos)?.type === schema.nodes.heading
      })

      return { collapsed, decorations: buildDecorations(newState.doc, collapsed, ystate) }
    },
  },
  props: {
    decorations(state) {
      return collapsibleHeadingsPluginKey.getState(state)?.decorations
    },
  },
})
