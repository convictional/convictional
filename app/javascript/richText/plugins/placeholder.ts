import { Plugin } from "prosemirror-state"
import { EditorView } from "prosemirror-view"

/**
 * Creates a ProseMirror plugin that displays placeholder text in an empty paragraph.
 *
 * @param placeholderText - The text to display as the placeholder.
 * @returns A ProseMirror plugin that adds a placeholder text to an empty paragraph.
 */
export default function placeholder(placeholderText: string): Plugin {
  const update = (view: EditorView) => {
    const doc = view.state.doc
    // content.size, not textContent: a leaf node like an image carries no text but is still content.
    const isEmpty =
      doc.childCount === 1 && doc.firstChild?.type.name === "paragraph" && doc.firstChild.content.size === 0

    if (isEmpty) {
      view.dom.setAttribute("data-placeholder", placeholderText)
    } else {
      view.dom.removeAttribute("data-placeholder")
    }
  }
  return new Plugin({
    view(view) {
      update(view)
      return { update }
    },
  })
}
