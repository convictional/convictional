import { expect, test, describe } from "vitest"
import { Plugin } from "prosemirror-state"
import { render } from "@testing-library/react"

import { Editor, EditorContent } from "../../../../../app/javascript/react/composites/editor/Editor"
import type { EditorFeature } from "../../../../../app/javascript/react/composites/editor/types"

describe("Editor", () => {
  test("renders without features", () => {
    const { container } = render(
      <Editor features={[]}>
        <EditorContent />
      </Editor>
    )
    expect(container.querySelector(".ProseMirror")).not.toBeNull()
  })

  test("renders children inside the editor", () => {
    const feature: EditorFeature = {
      plugins: [],
    }

    const { container } = render(
      <Editor features={[feature]}>
        <EditorContent />
        <div data-testid="feature-ui">hello</div>
      </Editor>
    )

    expect(container.querySelector("[data-testid='feature-ui']")).not.toBeNull()
  })

  test("applies className to contenteditable via plugin", () => {
    const { container } = render(
      <Editor features={[]} className="my-editor">
        <EditorContent />
      </Editor>
    )

    expect(container.querySelector(".my-editor")).not.toBeNull()
  })

  test("renders placeholder text", () => {
    const { container } = render(
      <Editor features={[]} placeholder="Type here...">
        <EditorContent />
      </Editor>
    )

    const editor = container.querySelector(".ProseMirror")
    expect(editor?.getAttribute("data-placeholder")).toBe("Type here...")
  })

  test("includes feature plugins in the editor", () => {
    // A plugin that adds a class to verify it's included
    const feature: EditorFeature = {
      plugins: [new Plugin({ props: { attributes: { "data-feature": "active" } } })],
    }

    const { container } = render(
      <Editor features={[feature]}>
        <EditorContent />
      </Editor>
    )

    expect(container.querySelector("[data-feature='active']")).not.toBeNull()
  })
})
