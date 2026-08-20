import type { Node } from "prosemirror-model"
import { EditorState, NodeSelection, TextSelection } from "prosemirror-state"
import { describe, expect, test } from "vitest"

import { getRange } from "~/react/composites/editor/features/comments/commentSelection"
import { getCommentMarkIds } from "~/richText/schema/commentMark"
import { schema } from "~/richText/schema"

function makeState(content: Node[]): EditorState {
  return EditorState.create({ doc: schema.node("doc", null, content), schema })
}
function makePara(...children: Node[]): Node {
  return schema.node("paragraph", null, children)
}
function image(attrs: { alt?: string | null; title?: string | null; src?: string } = {}): Node {
  return schema.node("image", { src: attrs.src ?? "x.png", alt: attrs.alt ?? null, title: attrs.title ?? null })
}

describe("getRange — text selections", () => {
  test("returns text and range for a text-only selection", () => {
    const state = makeState([makePara(schema.text("hello world"))])
    const selection = TextSelection.create(state.doc, 1, 12)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 0, to: 0 })

    expect(result).toEqual({ from: 1, to: 12, text: "hello world" })
  })

  test("returns the selected text when range covers text plus an image — text branch wins over image branch", () => {
    const state = makeState([makePara(schema.text("hello "), image({ alt: "ignored" }), schema.text(" world"))])
    const selection = TextSelection.create(state.doc, 1, 14)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 0, to: 0 })

    expect(result?.text).toBe("hello  world")
    expect(result?.text).not.toBe("ignored")
    expect(result?.from).toBe(1)
    expect(result?.to).toBe(14)
  })

  test("returns null for a collapsed selection in an empty paragraph", () => {
    const state = makeState([makePara()])
    const selection = TextSelection.create(state.doc, 1, 1)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 0, to: 0 })

    expect(result).toBeNull()
  })
})

describe("getRange — image selections", () => {
  test("returns the image's alt as text for a NodeSelection on an image with alt", () => {
    const state = makeState([makePara(image({ alt: "Sunset" }))])
    const selection = NodeSelection.create(state.doc, 1)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 0, to: 0 })

    expect(result).toEqual({ from: 1, to: 2, text: "Sunset" })
  })

  test("falls back to title when alt is empty", () => {
    const state = makeState([makePara(image({ alt: "", title: "My photo" }))])
    const selection = NodeSelection.create(state.doc, 1)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 0, to: 0 })

    expect(result?.text).toBe("My photo")
  })

  test("falls back to 'Image' when both alt and title are null", () => {
    const state = makeState([makePara(image({ alt: null, title: null }))])
    const selection = NodeSelection.create(state.doc, 1)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 0, to: 0 })

    expect(result?.text).toBe("Image")
  })

  test("falls back to 'Image' when alt and title are whitespace-only strings", () => {
    const state = makeState([makePara(image({ alt: "   ", title: "" }))])
    const selection = NodeSelection.create(state.doc, 1)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 0, to: 0 })

    expect(result?.text).toBe("Image")
  })

  test("expands a collapsed selection inside an image-only paragraph to the image range and uses alt", () => {
    const state = makeState([makePara(image({ alt: "Sunset" }))])
    const selection = TextSelection.create(state.doc, 1, 1)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 0, to: 0 })

    expect(result?.from).toBe(1)
    expect(result?.to).toBe(2)
    expect(result?.text).toBe("Sunset")
  })
})

describe("getRange — saved-selection fallback", () => {
  test("uses savedSelection when the current selection is collapsed and the saved range is non-empty", () => {
    const state = makeState([makePara(schema.text("hello world"))])
    const selection = TextSelection.create(state.doc, 6, 6)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 1, to: 6 })

    expect(result).toEqual({ from: 1, to: 6, text: "hello" })
  })

  test("uses savedSelection when it covers an image-only range and the current selection is collapsed", () => {
    const state = makeState([makePara(image({ alt: "Sunset" }))])
    const selection = TextSelection.create(state.doc, 1, 1)
    const stateWithSelection = state.apply(state.tr.setSelection(selection))

    const result = getRange(stateWithSelection, { from: 1, to: 2 })

    expect(result).toEqual({ from: 1, to: 2, text: "Sunset" })
  })
})

describe("comment mark attaches to image nodes", () => {
  test("tr.addMark over an image range attaches the comment mark to the image node", () => {
    const state = makeState([makePara(image({ alt: "Sunset" }))])
    const markType = schema.marks.comment
    const newState = EditorState.create({
      doc: state.apply(state.tr.addMark(1, 2, markType.create({ commentId: "test-id" }))).doc,
      schema,
    })

    expect(getCommentMarkIds(newState.doc).has("test-id")).toBe(true)
  })
})
