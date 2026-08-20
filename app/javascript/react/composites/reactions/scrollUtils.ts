// WebKit (Safari) adjusts window.scrollY when the DOM mutates while a
// contenteditable element (the chat composer) is focused — an undocumented
// heuristic that anchors the editing context. A reaction toggle's optimistic
// re-render trips it. Snapshot scrollY before the action and restore on the
// next frame; on browsers that don't move scroll, before === after and the
// restore is a no-op.
export function withScrollPreserved(action: () => void) {
  const beforeY = window.scrollY
  action()
  requestAnimationFrame(() => {
    if (window.scrollY !== beforeY) {
      window.scrollTo({ top: beforeY, behavior: "instant" })
    }
  })
}
