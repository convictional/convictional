import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { createRef } from "react"
import { afterEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/composites/chat/ChatComposerEditor", () => import("../../shared/chatEditorMock"))

import { editorCapture } from "../../shared/chatEditorMock"
import {
  CommentRichTextField,
  type CommentRichTextFieldHandle,
} from "~/react/composites/editor/components/comments/CommentRichTextField"

const users = [{ id: "u1", display_name: "Alice", is_collaborator: true }]

afterEach(() => {
  cleanup()
  editorCapture.lastProps = null
})

describe("CommentRichTextField", () => {
  test("drives the shared editor with comment-flavoured config and forwards props", () => {
    render(
      <CommentRichTextField
        initialContent="hello"
        placeholder="Add a comment..."
        mentionableUsers={users}
        className="my-box"
        onSend={vi.fn()}
      />
    )

    const props = editorCapture.lastProps
    // Comment surfaces submit on Cmd/Ctrl+Enter, never plain Enter, and never upload.
    expect(props.submitOn).toBe("mod-enter")
    expect(props.uploadUrl).toBeNull()
    expect(props.onEditPrevious()).toBe(false)
    expect(typeof props.claimId).toBe("string")
    // Pass-through props.
    expect(props.placeholder).toBe("Add a comment...")
    expect(props.initialContent).toBe("hello")
    expect(props.mentionableUsers).toEqual(users)
    expect(props.className).toBe("my-box")
  })

  test("submit() re-serializes the live doc through the parent's onSend", () => {
    const onSend = vi.fn()
    const ref = createRef<CommentRichTextFieldHandle>()
    render(<CommentRichTextField ref={ref} mentionableUsers={users} onSend={onSend} />)

    fireEvent.change(screen.getByTestId("chat-editor"), { target: { value: "typed text" } })
    ref.current?.submit()

    expect(onSend).toHaveBeenCalledWith("typed text")
  })

  test("Escape invokes onEscape for edit/reply surfaces", () => {
    const onEscape = vi.fn()
    render(<CommentRichTextField mentionableUsers={users} onSend={vi.fn()} onEscape={onEscape} />)

    fireEvent.keyDown(screen.getByTestId("chat-editor"), { key: "Escape" })
    expect(onEscape).toHaveBeenCalled()
  })
})
