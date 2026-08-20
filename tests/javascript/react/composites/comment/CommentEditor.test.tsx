import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

const capture = vi.hoisted(() => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  lastEditorProps: null as any,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  lastMentionableArg: null as any,
  klipyApiKey: "klipy-key" as string | null,
  sendSpy: vi.fn(),
}))

vi.mock("~/react/composites/chat/ChatComposerEditor", async () => {
  const React = await import("react")
  return {
    ChatComposerEditor: React.forwardRef(function ChatComposerEditor(props: Record<string, unknown>, ref) {
      capture.lastEditorProps = props
      React.useImperativeHandle(ref, () => ({
        focus: () => {},
        send: capture.sendSpy,
        triggerUpload: () => {},
        uploadFiles: () => {},
        insertImage: () => {},
        getReferencedAttachmentIds: () => [],
      }))
      return <div data-testid="chat-editor">Editor</div>
    }),
  }
})

vi.mock("~/react/composites/editor/components/GifPicker", () => ({
  GifPicker: () => <div data-testid="gif-picker" />,
}))

const mentionCandidates = [{ id: "u1", display_name: "Alice", is_collaborator: true }]
vi.mock("~/react/shared/hooks/useMentionableUsers", () => ({
  useMentionableUsers: (arg: unknown) => {
    capture.lastMentionableArg = arg
    return mentionCandidates
  },
}))

vi.mock("~/react/shared/hooks/useWorkspaceCollaboratorIds", () => ({
  useWorkspaceCollaboratorIds: (workspaceId: string | null) => (workspaceId ? new Set(["u1"]) : undefined),
}))

vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ clientConfig: { klipy_api_key: capture.klipyApiKey } }),
}))

import { CommentEditor } from "~/react/composites/comment/CommentEditor"

afterEach(() => {
  cleanup()
  capture.lastEditorProps = null
  capture.lastMentionableArg = null
  capture.klipyApiKey = "klipy-key"
  capture.sendSpy.mockClear()
})

describe("CommentEditor", () => {
  test("seeds the shared editor with the comment, autofocuses, and shows attach/GIF + Save/Cancel", () => {
    render(<CommentEditor initialContent="hello **world**" workspaceId="w1" onSave={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByTestId("chat-editor")).toBeInTheDocument()
    expect(capture.lastEditorProps.initialContent).toBe("hello **world**")
    expect(capture.lastEditorProps.autoFocus).toBe(true)
    expect(screen.getByRole("button", { name: "Attach file" })).toBeInTheDocument()
    expect(screen.getByTestId("gif-picker")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument()

    cleanup()
    capture.klipyApiKey = null
    render(<CommentEditor initialContent="x" workspaceId="w1" onSave={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByRole("button", { name: "Attach file" })).toBeInTheDocument()
    expect(screen.queryByTestId("gif-picker")).not.toBeInTheDocument()
  })

  test("Save routes through the editor handle; Cancel and Escape return without saving", () => {
    const onCancel = vi.fn()
    render(<CommentEditor initialContent="hi" workspaceId="w1" onSave={vi.fn()} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole("button", { name: "Save" }))
    expect(capture.sendSpy).toHaveBeenCalledOnce()

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onCancel).toHaveBeenCalledOnce()

    fireEvent.keyDown(screen.getByTestId("chat-editor"), { key: "Escape" })
    expect(onCancel).toHaveBeenCalledTimes(2)
  })

  test("keeps the editor open and re-enables Save when a save rejects", async () => {
    // A rejected save must not close the editor — the user keeps their edited text
    // and can retry. This is what lets EmailThreadShow's handleEditComment re-throw
    // (matching chat) instead of swallowing and discarding the edit.
    const onSave = vi.fn().mockRejectedValue(new Error("boom"))
    const onCancel = vi.fn()
    render(<CommentEditor initialContent="hi" workspaceId="w1" onSave={onSave} onCancel={onCancel} />)

    // Drive the real handleSave (the editor's onSend); the mocked send() is a no-op.
    await act(async () => {
      await capture.lastEditorProps.onSend("edited text")
    })

    expect(onSave).toHaveBeenCalledWith("edited text", expect.any(String))
    expect(onCancel).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Save" })).not.toBeDisabled()
  })

  test("forwards submitOn so post comment editing can keep Cmd/Ctrl+Enter to save", () => {
    render(
      <CommentEditor
        initialContent="hi"
        workspaceId="w1"
        submitOn="mod-enter"
        onSave={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(capture.lastEditorProps.submitOn).toBe("mod-enter")
  })

  test("scopes mentions to collaborators only when asked", () => {
    render(
      <CommentEditor
        initialContent="hi"
        workspaceId="w1"
        onSave={vi.fn()}
        onCancel={vi.fn()}
        scopeMentionsToCollaborators
      />
    )
    expect(capture.lastMentionableArg).toEqual({ collaboratorIds: new Set(["u1"]) })

    cleanup()
    // Post comments mention org-wide: no collaboratorIds passed.
    render(<CommentEditor initialContent="hi" workspaceId="w1" onSave={vi.fn()} onCancel={vi.fn()} />)
    expect(capture.lastMentionableArg).toBeUndefined()
  })
})
