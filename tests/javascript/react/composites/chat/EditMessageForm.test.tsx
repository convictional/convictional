import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

// Shared mutable state captured by the editor mock so tests can inspect the
// props EditMessageForm passes down. ChatComposerEditor depends on ProseMirror
// internals that don't run in jsdom, so we replace it with a stub that renders
// a plain testable element.
const editorMock = vi.hoisted(() => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  lastProps: null as any,
}))

vi.mock("~/react/composites/chat/ChatComposerEditor", async () => {
  const React = await import("react")
  return {
    ChatComposerEditor: React.forwardRef(function ChatComposerEditor(props: Record<string, unknown>, ref) {
      editorMock.lastProps = props
      React.useImperativeHandle(ref, () => ({
        focus: () => {},
        send: () => {},
        triggerUpload: () => {},
        uploadFiles: () => {},
        insertImage: () => {},
        getReferencedAttachmentIds: () => [],
      }))
      return <div data-testid="chat-editor">Editor</div>
    }),
  }
})

import { EditMessageForm } from "~/react/composites/chat/EditMessageForm"

afterEach(() => {
  cleanup()
  editorMock.lastProps = null
})

describe("EditMessageForm", () => {
  test("mounts ChatComposerEditor (not a plain textarea) and forwards mention candidates", () => {
    const mentionableUsers = [{ id: "u1", display_name: "Alice", is_collaborator: true }]
    render(
      <EditMessageForm
        initialContent="Hello @[Alice]"
        uploadUrl="/api/upload"
        mentionableUsers={mentionableUsers}
        mentionsEnabled
        klipyApiKey={null}
        onSave={async () => {}}
        onCancel={() => {}}
      />
    )

    // The bug: EditMessageForm currently renders a raw <textarea>, which can't
    // produce the @[Display Name] mention tokens the backend expects on edit.
    // After the fix the form must mount ChatComposerEditor instead, with the
    // mention candidates threaded through so @ autocomplete is available during edit.
    expect(screen.getByTestId("chat-editor")).toBeInTheDocument()
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
    expect(editorMock.lastProps).not.toBeNull()
    expect(editorMock.lastProps.mentionableUsers).toEqual(mentionableUsers)
    expect(editorMock.lastProps.initialContent).toBe("Hello @[Alice]")
    // With uploadUrl present, the attach button must render so users can add
    // attachments while editing.
    expect(screen.getByRole("button", { name: "Attach file" })).toBeInTheDocument()
  })

  test("Save is disabled when the form opens with empty content", () => {
    render(
      <EditMessageForm
        initialContent=""
        uploadUrl={null}
        mentionableUsers={[]}
        klipyApiKey={null}
        onSave={async () => {}}
        onCancel={() => {}}
      />
    )

    // Independent of whether the input is a textarea or ChatComposerEditor,
    // an empty edit must not be submittable.
    const saveButton = screen.getByRole("button", { name: "Save" })
    expect(saveButton).toBeDisabled()
  })
})
