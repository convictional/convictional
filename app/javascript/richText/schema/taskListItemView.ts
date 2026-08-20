import { Node } from "prosemirror-model"
import { EditorView, NodeView } from "prosemirror-view"

export class TaskListItemView implements NodeView {
  dom: HTMLElement
  contentDOM: HTMLElement

  constructor(node: Node, view: EditorView, getPos: () => number | undefined) {
    const checkbox = document.createElement("input")
    checkbox.type = "checkbox"
    checkbox.className = "task-checkbox"
    checkbox.tabIndex = -1
    if (node.attrs["checked"]) {
      checkbox.checked = true
    }
    checkbox.addEventListener("click", e => {
      const pos = getPos()
      if (pos === undefined) return
      e.preventDefault()
      view.dispatch(view.state.tr.setNodeAttribute(pos, "checked", !node.attrs["checked"]))
    })

    const checkboxWrap = document.createElement("span")
    checkboxWrap.contentEditable = "false"
    checkboxWrap.className = "task-checkbox-wrap"
    checkboxWrap.appendChild(checkbox)

    this.contentDOM = document.createElement("div")
    this.contentDOM.className = "task-content"

    this.dom = document.createElement("li")
    this.dom.className = "task-list-item"
    this.dom.appendChild(checkboxWrap)
    this.dom.appendChild(this.contentDOM)
  }

  stopEvent(event: Event): boolean {
    return event.target instanceof HTMLInputElement
  }
}
