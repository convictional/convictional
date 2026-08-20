import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { Editor, EditorContent } from "~/react/composites/editor/Editor"
import { useEnterToSend } from "~/react/composites/editor/features/useEnterToSend"
import { parse } from "~/richText/schema"

// useEnterToSend is the shared submit chokepoint for every comment/message
// composer that isn't the bespoke PostCommentComposer. It must submit ONLY the
// composer and never let the keystroke reach an ancestor keydown handler — the
// regression that let ⌘↵ on a draft comment also publish the post, because an
// ancestor listener on PostDraftEditor fired on the same keystroke.

function SendHarness({
  onSend,
  requireModifier,
  content = "hello world",
}: {
  onSend: (markdown: string) => void
  requireModifier: boolean
  content?: string
}) {
  const feature = useEnterToSend({ onSend, requireModifier })
  return (
    <Editor features={[feature]} doc={parse(content)}>
      <EditorContent />
    </Editor>
  )
}

function renderWithAncestor(ui: React.ReactElement) {
  const ancestorSpy = vi.fn()
  const utils = render(<div onKeyDown={ancestorSpy}>{ui}</div>)
  const editable = utils.container.querySelector<HTMLElement>(".ProseMirror")
  if (!editable) throw new Error("editor did not mount")
  return { ancestorSpy, editable, ...utils }
}

function pressEnter(editable: HTMLElement, modifier: "meta" | "ctrl" | "none") {
  const event = new KeyboardEvent("keydown", {
    key: "Enter",
    metaKey: modifier === "meta",
    ctrlKey: modifier === "ctrl",
    bubbles: true,
    cancelable: true,
  })
  editable.dispatchEvent(event)
  return event
}

describe("useEnterToSend hotkey submit", () => {
  // Covers post-draft inline comments, comment edits, goal comments, and
  // email-thread comments (all submitOn "mod-enter").
  it.each([["meta"], ["ctrl"]] as const)(
    "mod-enter (%s) submits the composer without the keystroke reaching an ancestor handler",
    modifier => {
      const onSend = vi.fn()
      const { ancestorSpy, editable } = renderWithAncestor(<SendHarness onSend={onSend} requireModifier />)

      pressEnter(editable, modifier)

      expect(onSend).toHaveBeenCalledExactlyOnceWith("hello world")
      expect(ancestorSpy).not.toHaveBeenCalled()
    }
  )

  // Covers chat messages and message edits (plain Enter sends).
  it("plain Enter submits the composer without the keystroke reaching an ancestor handler", () => {
    const onSend = vi.fn()
    const { ancestorSpy, editable } = renderWithAncestor(<SendHarness onSend={onSend} requireModifier={false} />)

    pressEnter(editable, "none")

    expect(onSend).toHaveBeenCalledExactlyOnceWith("hello world")
    expect(ancestorSpy).not.toHaveBeenCalled()
  })

  // The fix is scoped to actual submits: a keystroke that does NOT submit (plain
  // Enter in a mod-enter composer inserts a newline) must still bubble, so it
  // isn't the stopPropagation swallowing every Enter.
  it("does not submit or stop propagation for a non-submitting Enter", () => {
    const onSend = vi.fn()
    const { ancestorSpy, editable } = renderWithAncestor(<SendHarness onSend={onSend} requireModifier />)

    pressEnter(editable, "none")

    expect(onSend).not.toHaveBeenCalled()
    expect(ancestorSpy).toHaveBeenCalledOnce()
  })
})
