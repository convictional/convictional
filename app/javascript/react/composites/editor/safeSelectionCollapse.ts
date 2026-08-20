// prosemirror-view's selectionToDOM calls Selection.collapse() unwrapped (only
// the subsequent extend() call is in try/catch). On Safari, react-prosemirror's
// commit phase can compute a DOM offset that's briefly out of range relative
// to the freshly-reconciled React tree, and collapse() throws IndexSizeError —
// which propagates into React's commit and tears down the editor island.
//
// Swallowing IndexSizeError is safe: the existing selection is retained for
// that frame, prosemirror reconverges on the next update. The alternative is
// a crashed compose bar (DECIDE-90F).
//
// Note: this patches Selection.prototype globally, so every consumer of
// window.getSelection().collapse(...) on the page swallows IndexSizeError —
// not just the editor. This is intentional and pragmatic; a scoped fix
// would require wrapping EditorView.dispatch/updateState inside ProseMirror.
// Non-editor code that depends on IndexSizeError propagating would be
// affected, but in practice nothing does.

const PATCHED_FLAG = "__convictionalSafeCollapse"

type CollapseFn = typeof Selection.prototype.collapse & { [PATCHED_FLAG]?: true }

export function installSafeSelectionCollapse() {
  if (typeof Selection === "undefined") return
  const current = Selection.prototype.collapse as CollapseFn
  // Source of truth lives on the function itself so Vite HMR can't stack
  // wrappers by re-running this module with a fresh module-scoped flag.
  if (current[PATCHED_FLAG]) return

  const original = current
  const wrapper: CollapseFn = function (this: Selection, node: Node | null, offset?: number) {
    try {
      return original.call(this, node, offset)
    } catch (err) {
      if (err instanceof DOMException && err.name === "IndexSizeError") return
      throw err
    }
  }
  wrapper[PATCHED_FLAG] = true
  Selection.prototype.collapse = wrapper
}
