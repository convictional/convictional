import { Plugin } from "prosemirror-state"
import { EditorView } from "prosemirror-view"

const MAX_HEIGHT_PX = 384
const MAX_VIEWPORT_RATIO = 0.4

function getMaxHeight(): number {
  const viewportHeight = window.visualViewport?.height ?? window.innerHeight
  return Math.min(MAX_HEIGHT_PX, viewportHeight * MAX_VIEWPORT_RATIO)
}

export default function autoExpand(): Plugin {
  const resize = (view: EditorView) => {
    const dom = view.dom as HTMLElement
    const maxHeight = getMaxHeight()
    dom.style.height = "auto"
    const scrollHeight = dom.scrollHeight
    const clampedHeight = Math.min(scrollHeight, maxHeight)
    dom.style.height = `${clampedHeight}px`
    dom.style.maxHeight = `${maxHeight}px`
    dom.style.overflowY = clampedHeight >= maxHeight ? "auto" : ""
  }

  return new Plugin({
    view(view) {
      resize(view)

      const onViewportResize = () => resize(view)
      window.visualViewport?.addEventListener("resize", onViewportResize)

      return {
        update(view, prevState) {
          if (view.state.doc === prevState.doc) return
          resize(view)
        },
        destroy() {
          window.visualViewport?.removeEventListener("resize", onViewportResize)
        },
      }
    },
  })
}
