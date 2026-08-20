import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

// ChatComposerEditor depends on ProseMirror internals that don't run in jsdom, so
// we replace it with a stub that captures the props CommentComposer passes down
// and exposes the imperative handle the buttons drive.
const capture = vi.hoisted(() => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  lastEditorProps: null as any,
  klipyApiKey: "klipy-key" as string | null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  composePreview: null as any,
  dismissed: false,
  resetSpy: vi.fn(),
  isMobile: false,
  focusSpy: vi.fn(),
}))

vi.mock("~/react/composites/chat/ChatComposerEditor", async () => {
  const React = await import("react")
  return {
    ChatComposerEditor: React.forwardRef(function ChatComposerEditor(props: Record<string, unknown>, ref) {
      capture.lastEditorProps = props
      React.useImperativeHandle(ref, () => ({
        focus: capture.focusSpy,
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

vi.mock("~/react/composites/editor/components/GifPicker", () => ({
  GifPicker: () => <div data-testid="gif-picker" />,
}))

vi.mock("~/react/composites/chat/LinkPreviewCard", () => ({
  LinkPreviewCard: () => <div data-testid="link-preview-card" />,
}))

vi.mock("~/react/shared/hooks/useLinkPreviewUnfurl", () => ({
  useLinkPreviewUnfurl: () => ({
    composePreview: capture.composePreview,
    dismissComposePreview: vi.fn(),
    dismissed: capture.dismissed,
    isUrlDismissed: () => capture.dismissed,
    reset: capture.resetSpy,
  }),
}))

vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ clientConfig: { klipy_api_key: capture.klipyApiKey } }),
}))

vi.mock("~/react/shared/hooks/useIsMobile", () => ({
  useIsMobile: () => capture.isMobile,
}))

import { createRef } from "react"

import { CommentComposer, type CommentComposerFocusHandle } from "~/react/composites/comment/CommentComposer"

const currentUser = { display_name: "Me", picture: null }
const mentionCandidates = [{ id: "u1", display_name: "Alice", is_collaborator: true }]

afterEach(() => {
  cleanup()
  capture.lastEditorProps = null
  capture.klipyApiKey = "klipy-key"
  capture.composePreview = null
  capture.dismissed = false
  capture.resetSpy.mockClear()
  capture.isMobile = false
  capture.focusSpy.mockClear()
})

function renderComposer(onSubmit = vi.fn().mockResolvedValue({ id: "c1" }), props = {}) {
  return render(
    <CommentComposer
      currentUser={currentUser}
      mentionableUsers={mentionCandidates}
      uploadUrl="/upload"
      onSubmit={onSubmit}
      placeholder="Say something"
      {...props}
    />
  )
}

describe("CommentComposer", () => {
  test("mounts the shared editor with the placeholder + mentions and the attach/send/GIF affordances", () => {
    renderComposer()
    expect(screen.getByTestId("chat-editor")).toBeInTheDocument()
    expect(capture.lastEditorProps.placeholder).toBe("Say something")
    expect(capture.lastEditorProps.mentionableUsers).toEqual(mentionCandidates)
    // Send key defaults to the shared editor's Enter behavior unless overridden.
    expect(capture.lastEditorProps.submitOn).toBeUndefined()
    expect(screen.getByRole("button", { name: "Attach file" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument()
    expect(screen.getByTestId("gif-picker")).toBeInTheDocument()

    cleanup()
    capture.klipyApiKey = null
    renderComposer()
    expect(screen.queryByTestId("gif-picker")).not.toBeInTheDocument()
  })

  test("Send is disabled until the editor reports non-empty content", () => {
    renderComposer()
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled()
    act(() => capture.lastEditorProps.onChange("hi"))
    expect(screen.getByRole("button", { name: "Send" })).not.toBeDisabled()
  })

  test("submits with the claim id + unfurl flag and rotates the claim id on success", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ id: "c1" })
    renderComposer(onSubmit)
    const claimBefore = capture.lastEditorProps.claimId

    await act(async () => {
      await capture.lastEditorProps.onSend("check https://example.com")
    })

    expect(onSubmit).toHaveBeenCalledWith("check https://example.com", claimBefore, true)
    // Success rotates the claim id (editor remounts clean) and clears any dismissal.
    expect(capture.lastEditorProps.claimId).not.toBe(claimBefore)
    expect(capture.resetSpy).toHaveBeenCalled()
  })

  test("passes unfurl_links=false when the previewed URL was dismissed", async () => {
    capture.dismissed = true
    const onSubmit = vi.fn().mockResolvedValue({ id: "c1" })
    renderComposer(onSubmit)
    await act(async () => {
      await capture.lastEditorProps.onSend("check https://example.com")
    })
    expect(onSubmit).toHaveBeenCalledWith("check https://example.com", expect.any(String), false)
  })

  test("keeps the draft (no rotation) and shows the error text when a submit fails", async () => {
    const onSubmit = vi.fn().mockResolvedValue(null)
    renderComposer(onSubmit, { errorText: "Couldn't send comment. Try again." })
    const claimBefore = capture.lastEditorProps.claimId

    await act(async () => {
      await capture.lastEditorProps.onSend("oops")
    })

    expect(capture.lastEditorProps.claimId).toBe(claimBefore)
    expect(screen.getByText("Couldn't send comment. Try again.")).toBeInTheDocument()
    expect(capture.resetSpy).not.toHaveBeenCalled()
  })

  test("renders the live link preview card only when the composer surfaces one", () => {
    renderComposer()
    expect(screen.queryByTestId("link-preview-card")).not.toBeInTheDocument()

    cleanup()
    capture.composePreview = { url: "https://example.com", title: "Example", description: "", image: null }
    renderComposer()
    expect(screen.getByTestId("link-preview-card")).toBeInTheDocument()
  })

  test("renders the mobile pill layout with a dedicated send button", () => {
    capture.isMobile = true
    capture.composePreview = { url: "https://example.com", title: "Example", description: "", image: null }
    renderComposer()
    expect(screen.getByTestId("chat-editor")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Attach file" })).toBeInTheDocument()
    expect(screen.getByTestId("gif-picker")).toBeInTheDocument()
    expect(screen.getByTestId("link-preview-card")).toBeInTheDocument()
  })

  test("renders the replyPreview banner above the editor in both layouts", () => {
    const banner = <div data-testid="reply-banner">quoting Alice</div>
    renderComposer(vi.fn(), { replyPreview: banner })
    expect(screen.getByTestId("reply-banner")).toBeInTheDocument()

    cleanup()
    capture.isMobile = true
    renderComposer(vi.fn(), { replyPreview: banner })
    expect(screen.getByTestId("reply-banner")).toBeInTheDocument()
  })

  test("Cancel-free inline variant renders without page chrome and uses the testId", () => {
    renderComposer(vi.fn(), { variant: "inline", testId: "reply-composer" })
    expect(screen.getByTestId("reply-composer")).toBeInTheDocument()
  })

  test("forwards submitOn so post surfaces can keep Cmd/Ctrl+Enter to send", () => {
    renderComposer(vi.fn(), { submitOn: "mod-enter" })
    expect(capture.lastEditorProps.submitOn).toBe("mod-enter")
  })

  test("defaults onEditPrevious to a no-op (posts keep native caret movement)", () => {
    renderComposer()
    // No callback supplied → the editor gets a function that declines to edit,
    // so ArrowUp is never consumed.
    expect(capture.lastEditorProps.onEditPrevious()).toBe(false)
  })

  test("forwards a provided onEditPrevious to the editor", () => {
    const onEditPrevious = vi.fn(() => true)
    renderComposer(vi.fn(), { onEditPrevious })
    expect(capture.lastEditorProps.onEditPrevious).toBe(onEditPrevious)
  })

  test("exposes a focus handle that focuses the underlying editor", () => {
    const ref = createRef<CommentComposerFocusHandle>()
    render(
      <CommentComposer
        ref={ref}
        currentUser={currentUser}
        mentionableUsers={mentionCandidates}
        uploadUrl="/upload"
        onSubmit={vi.fn()}
        placeholder="Say something"
      />
    )
    ref.current?.focus()
    expect(capture.focusSpy).toHaveBeenCalledOnce()
  })
})
