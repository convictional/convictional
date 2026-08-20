import { Plugin, PluginKey, type EditorState } from "prosemirror-state"
import { Decoration, DecorationSet, type EditorView } from "prosemirror-view"
import { absolutePositionToRelativePosition, relativePositionToAbsolutePosition, ySyncPluginKey } from "y-prosemirror"
import type { Doc, RelativePosition, XmlFragment } from "yjs"

import { COMMENT_HIGHLIGHT_CLASS, COMMENT_ID_ATTR } from "~/richText/schema/commentMark"

// The Yjs↔ProseMirror position map y-prosemirror threads through its helpers;
// not exported by name, so recover it from the helper signature.
type ProsemirrorMapping = Parameters<typeof absolutePositionToRelativePosition>[2]

// An unsaved comment highlight is a local-only decoration, never a doc mark, so
// it stays out of the shared Yjs document. If it were a mark it would sync to
// peers, who — unable to tell an in-progress pending mark from a genuine orphan —
// would strip it via cleanupOrphanMarks and broadcast the removal back, deleting
// the author's highlight mid-compose. The real `comment` mark is added only once
// the comment is saved (commitPendingComment), at which point it has a backing
// thread and correctly syncs.
//
// The catch: y-prosemirror applies every *remote* change by replacing the whole
// document (sync-plugin `_typeChanged`), and mapping a decoration through that
// replace-all drops it. So a peer typing anywhere would wipe the author's pending
// highlight. We anchor each pending highlight to Yjs relative positions and
// recompute the decoration from them on remote changes — the same technique
// y-prosemirror's yCursorPlugin uses to keep remote cursors alive across edits.

type PendingCommentMeta =
  { add: { id: string; from: number; to: number }; remove?: never } | { add?: never; remove: { id: string } }

// from/to are the positions captured when the highlight was opened; they anchor
// the decoration in a non-collaborative editor (no Yjs binding) and seed the
// relative positions when there is one.
interface PendingAnchor {
  id: string
  relFrom: RelativePosition | null
  relTo: RelativePosition | null
  from: number
  to: number
}

interface PendingCommentState {
  pending: PendingAnchor[]
  decorations: DecorationSet
}

// Minimal shape of the ySyncPlugin state we read (its key is typed as `any`).
interface YSyncState {
  doc: Doc
  type: XmlFragment
  binding: { mapping: ProsemirrorMapping } | null
  isChangeOrigin: boolean
}

const pendingCommentPluginKey = new PluginKey<PendingCommentState>("pendingComment")

function decorationAttrs(id: string) {
  return { class: COMMENT_HIGHLIGHT_CLASS, [COMMENT_ID_ATTR]: id }
}

function makeAnchor(id: string, from: number, to: number, ystate: YSyncState | undefined): PendingAnchor {
  if (ystate?.binding) {
    return {
      id,
      relFrom: absolutePositionToRelativePosition(from, ystate.type, ystate.binding.mapping),
      relTo: absolutePositionToRelativePosition(to, ystate.type, ystate.binding.mapping),
      from,
      to,
    }
  }
  return { id, relFrom: null, relTo: null, from, to }
}

function resolveAnchor(anchor: PendingAnchor, ystate: YSyncState | undefined): { from: number; to: number } | null {
  let { from, to } = anchor
  if (anchor.relFrom && anchor.relTo && ystate?.binding && ystate.binding.mapping.size > 0) {
    const resolvedFrom = relativePositionToAbsolutePosition(
      ystate.doc,
      ystate.type,
      anchor.relFrom,
      ystate.binding.mapping
    )
    const resolvedTo = relativePositionToAbsolutePosition(
      ystate.doc,
      ystate.type,
      anchor.relTo,
      ystate.binding.mapping
    )
    if (resolvedFrom == null || resolvedTo == null) return null
    from = resolvedFrom
    to = resolvedTo
  }
  if (from >= to) return null
  return { from, to }
}

function buildDecorations(
  doc: EditorState["doc"],
  pending: PendingAnchor[],
  ystate: YSyncState | undefined
): DecorationSet {
  const decorations: Decoration[] = []
  for (const anchor of pending) {
    const range = resolveAnchor(anchor, ystate)
    if (!range || range.to > doc.content.size) continue
    decorations.push(Decoration.inline(range.from, range.to, decorationAttrs(anchor.id), { id: anchor.id }))
  }
  return DecorationSet.create(doc, decorations)
}

export const pendingCommentPlugin = new Plugin<PendingCommentState>({
  key: pendingCommentPluginKey,
  state: {
    init() {
      return { pending: [], decorations: DecorationSet.empty }
    },
    apply(tr, value, _oldState, newState) {
      const ystate = ySyncPluginKey.getState(newState) as YSyncState | undefined
      const meta = tr.getMeta(pendingCommentPluginKey) as PendingCommentMeta | undefined

      let pending = value.pending
      if (meta?.add) {
        const { id, from, to } = meta.add
        pending = [...pending.filter(a => a.id !== id), makeAnchor(id, from, to, ystate)]
      } else if (meta?.remove) {
        const removeId = meta.remove.id
        pending = pending.filter(a => a.id !== removeId)
      }

      // A remote change replaces the whole doc, dropping mapped decorations —
      // recompute from the relative anchors. Meta changes also rebuild. A plain
      // local edit just maps the current decorations forward.
      const rebuild = meta != null || ystate?.isChangeOrigin === true
      const decorations = rebuild
        ? buildDecorations(newState.doc, pending, ystate)
        : value.decorations.map(tr.mapping, tr.doc)

      return { pending, decorations }
    },
  },
  props: {
    decorations(state) {
      return pendingCommentPluginKey.getState(state)?.decorations
    },
  },
})

export function addPendingCommentDecoration(view: EditorView, id: string, from: number, to: number): void {
  if (from === to) return
  view.dispatch(view.state.tr.setMeta(pendingCommentPluginKey, { add: { id, from, to } }))
}

export function clearPendingCommentDecoration(view: EditorView, id: string): void {
  view.dispatch(view.state.tr.setMeta(pendingCommentPluginKey, { remove: { id } }))
}

// Promote the pending decoration to a real `comment` mark at its CURRENT range —
// tracked through any edits (local or remote) since the comment was opened — and
// drop the decoration in the same transaction so the highlight never flickers.
export function commitPendingComment(view: EditorView, id: string): void {
  const state = pendingCommentPluginKey.getState(view.state)
  const found = state?.decorations.find(undefined, undefined, (spec: { id: string }) => spec.id === id)

  // Prefer the decoration's range — it carries the position mapped forward through
  // every edit since the comment opened. If the decoration set lags (or was cleared
  // by a double-call/unmount race), recompute from the anchor's Yjs relative
  // positions so a saved comment still gets its highlight.
  let range = found?.length && found[0].from < found[0].to ? { from: found[0].from, to: found[0].to } : null
  if (!range) {
    const anchor = state?.pending.find(a => a.id === id)
    const ystate = ySyncPluginKey.getState(view.state) as YSyncState | undefined
    const resolved = anchor ? resolveAnchor(anchor, ystate) : null
    range = resolved && resolved.to <= view.state.doc.content.size ? resolved : null
  }

  if (!range) {
    // The anchored text was deleted before the save landed — there is no correct
    // place for the mark. Surface it rather than silently orphaning the thread.
    console.warn(`commitPendingComment: no live range for comment "${id}"; highlight not applied`)
    return
  }

  const markType = view.state.schema.marks.comment
  if (!markType) return

  view.dispatch(
    view.state.tr
      .addMark(range.from, range.to, markType.create({ commentId: id }))
      .setMeta(pendingCommentPluginKey, { remove: { id } })
  )
}
