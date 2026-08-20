// Ref-counted page scroll lock shared by every modal overlay, so stacked
// overlays don't unlock the page early. Framework-agnostic so both React
// (useScrollLock) and plain modules (pullToRefresh) share one source of truth
// for whether an overlay currently owns scrolling — nobody has to infer it from
// the DOM side effects below.
//
// On lock we collapse the always-on stable gutter (main.css) and replace it with
// an equal padding-right: the backdrop then reaches the true viewport edge (no
// undimmed strip) while content width stays fixed (no shift). Standard
// scrollbar compensation; padding is 0 for overlay scrollbars.
let lockCount = 0
const previous = { overflow: "", paddingRight: "", scrollbarGutter: "" }

export function lockScroll(): void {
  if (lockCount === 0) {
    const el = document.documentElement
    const gutterWidth = window.innerWidth - el.clientWidth
    previous.overflow = el.style.overflow
    previous.paddingRight = el.style.paddingRight
    previous.scrollbarGutter = el.style.scrollbarGutter
    el.style.overflow = "hidden"
    el.style.scrollbarGutter = "auto"
    if (gutterWidth > 0) el.style.paddingRight = `${gutterWidth}px`
  }
  lockCount += 1
}

export function unlockScroll(): void {
  lockCount = Math.max(0, lockCount - 1)
  if (lockCount === 0) {
    const el = document.documentElement
    el.style.overflow = previous.overflow
    el.style.scrollbarGutter = previous.scrollbarGutter
    el.style.paddingRight = previous.paddingRight
  }
}

export function isScrollLocked(): boolean {
  return lockCount > 0
}
