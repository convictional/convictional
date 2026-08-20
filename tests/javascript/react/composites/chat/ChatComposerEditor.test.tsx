import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ChatComposerEditor } from "~/react/composites/chat/ChatComposerEditor"

// ChatComposerEditor is the shared composer behind most comment/message
// surfaces. Mounting it for real verifies the whole composer wiring — not just
// the hook — keeps a hotkey submit from reaching an ancestor keydown handler,
// which is how ⌘↵ on a draft comment used to also publish the post.

function renderComposer(props: { submitOn: "enter" | "mod-enter"; onSend: (content: string) => void }) {
  const ancestorSpy = vi.fn()
  const { container } = render(
    <div onKeyDown={ancestorSpy}>
      <ChatComposerEditor
        onSend={props.onSend}
        onChange={() => {}}
        onEditPrevious={() => false}
        uploadUrl={null}
        mentionableUsers={[]}
        claimId="test-claim"
        initialContent="hello world"
        submitOn={props.submitOn}
      />
    </div>
  )
  const editable = container.querySelector<HTMLElement>(".ProseMirror")
  if (!editable) throw new Error("editor did not mount")
  return { ancestorSpy, editable }
}

function pressEnter(editable: HTMLElement, withModifier: boolean) {
  const event = new KeyboardEvent("keydown", {
    key: "Enter",
    metaKey: withModifier,
    bubbles: true,
    cancelable: true,
  })
  editable.dispatchEvent(event)
  return event
}

describe("ChatComposerEditor hotkey submit", () => {
  // Post-draft inline comments, goal comments, and email-thread comments.
  it("mod-enter submits only the composer, not an ancestor handler", () => {
    const onSend = vi.fn()
    const { ancestorSpy, editable } = renderComposer({ submitOn: "mod-enter", onSend })

    pressEnter(editable, true)

    expect(onSend).toHaveBeenCalledExactlyOnceWith("hello world")
    expect(ancestorSpy).not.toHaveBeenCalled()
  })

  // Chat messages (plain Enter sends).
  it("plain Enter submits only the composer, not an ancestor handler", () => {
    const onSend = vi.fn()
    const { ancestorSpy, editable } = renderComposer({ submitOn: "enter", onSend })

    pressEnter(editable, false)

    expect(onSend).toHaveBeenCalledExactlyOnceWith("hello world")
    expect(ancestorSpy).not.toHaveBeenCalled()
  })
})
