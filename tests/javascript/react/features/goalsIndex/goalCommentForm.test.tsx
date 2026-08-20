import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/composites/chat/ChatComposerEditor", () => import("../../shared/chatEditorMock"))

import { editorCapture } from "../../shared/chatEditorMock"
import { CommentForm } from "../../../../../app/javascript/react/composites/CommentForm"

const MENTION_USERS = [
  { id: "u1", display_name: "Alice Admin", is_collaborator: true },
  { id: "u2", display_name: "Bob Builder", is_collaborator: false },
]

afterEach(() => {
  cleanup()
  editorCapture.lastProps = null
  vi.restoreAllMocks()
})

describe("goal CommentForm", () => {
  test("mounts the rich-text editor with the placeholder, mentions, and mod-enter submit", () => {
    render(<CommentForm mentionableUsers={MENTION_USERS} onSubmit={vi.fn()} placeholder="Reply..." />)

    expect(screen.getByTestId("chat-editor")).toBeTruthy()
    expect(editorCapture.lastProps.placeholder).toBe("Reply...")
    expect(editorCapture.lastProps.mentionableUsers).toEqual(MENTION_USERS)
    expect(editorCapture.lastProps.submitOn).toBe("mod-enter")
  })

  test("submit is disabled until there is content, then sends the typed markdown", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<CommentForm mentionableUsers={MENTION_USERS} onSubmit={onSubmit} />)

    const button = screen.getByRole("button")
    expect(button).toBeDisabled()

    fireEvent.change(screen.getByTestId("chat-editor"), { target: { value: "looks good" } })
    expect(button).not.toBeDisabled()

    fireEvent.click(button)
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("looks good"))
  })
})
