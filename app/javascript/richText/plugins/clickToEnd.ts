import { Plugin, Selection } from "prosemirror-state"

// ProseMirror defers click caret placement to the browser. When the editor is
// taller than its content (e.g. a near-empty meeting agenda), Chrome resolves a
// click in the empty space below the text to document position 0, so the user's
// next keystroke is prepended. Redirect such clicks to the end of the document.
export const clickToEnd = new Plugin({
  props: {
    handleClick(view, _pos, event) {
      // event.target is the editor element itself only when the click landed on
      // its padding; clicking actual text reports an inner node, which we leave alone.
      if (event.target !== view.dom) return false

      const lastChild = view.dom.lastElementChild
      if (lastChild && event.clientY <= lastChild.getBoundingClientRect().bottom) return false

      view.dispatch(view.state.tr.setSelection(Selection.atEnd(view.state.doc)).scrollIntoView())
      return true
    },
  },
})
