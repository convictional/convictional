import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

// EmailThreadCommentForm is a thin wrapper over the shared CommentComposer; stub
// the composer to capture the props the form threads down (mentions scope,
// placeholder, error copy, and the submit wiring to useCommentSubmit).
const capture = vi.hoisted(() => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  lastComposerProps: null as any,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  lastMentionableArg: null as any,
  sendSpy: vi.fn().mockResolvedValue({ id: "c-new" }),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  submitOnSuccess: null as any,
  focusSpy: vi.fn(),
}))

vi.mock("~/react/composites/comment/CommentComposer", async () => {
  const React = await import("react")
  return {
    // forwardRef so the form's forwarded focus handle is exercised.
    CommentComposer: React.forwardRef((props: Record<string, unknown>, ref) => {
      capture.lastComposerProps = props
      React.useImperativeHandle(ref, () => ({ focus: capture.focusSpy }))
      return <div data-testid="comment-composer" />
    }),
  }
})

const mentionCandidates = [{ id: "u1", display_name: "Alice Admin", is_collaborator: true }]
vi.mock("~/react/shared/hooks/useMentionableUsers", () => ({
  useMentionableUsers: (arg: unknown) => {
    capture.lastMentionableArg = arg
    return mentionCandidates
  },
}))

vi.mock("~/react/shared/hooks/useWorkspaceCollaboratorIds", () => ({
  useWorkspaceCollaboratorIds: () => new Set(["u1"]),
}))

vi.mock("~/react/features/emailThreadShow/hooks/useCommentSubmit", () => ({
  useCommentSubmit: (opts: { onSuccess?: (c: unknown) => void }) => {
    capture.submitOnSuccess = opts.onSuccess
    return { send: capture.sendSpy, sending: false, error: false }
  },
}))

vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ user: { id: "me", display_name: "Me", picture: null } }),
}))

import { createRef } from "react"

import { EmailThreadCommentForm } from "~/react/features/emailThreadShow/components/EmailThreadCommentForm"
import type { CommentComposerFocusHandle } from "~/react/composites/comment/CommentComposer"

afterEach(() => {
  cleanup()
  capture.lastComposerProps = null
  capture.lastMentionableArg = null
  capture.sendSpy.mockClear()
  capture.submitOnSuccess = null
  capture.focusSpy.mockClear()
})

describe("EmailThreadCommentForm", () => {
  test("renders the shared composer with the email placeholder, error copy, and avatar", () => {
    render(<EmailThreadCommentForm workspaceId="w1" threadId="t1" />)
    expect(screen.getByTestId("comment-composer")).toBeInTheDocument()
    expect(capture.lastComposerProps.placeholder).toBe("Write an internal chat message")
    expect(capture.lastComposerProps.errorText).toBe("Couldn't send comment. Try again.")
    expect(capture.lastComposerProps.testId).toBe("comment-form")
    expect(capture.lastComposerProps.currentUser).toEqual({ display_name: "Me", picture: null })
    expect(capture.lastComposerProps.mentionableUsers).toEqual(mentionCandidates)
  })

  test("scopes mentions to the thread's collaborators (keeps the Collaborators split)", () => {
    // Email threads DO expose collaborators, so the form must pass collaboratorIds —
    // without it, mentions would go org-wide and the "added collaborators don't
    // appear" bug would return.
    render(<EmailThreadCommentForm workspaceId="w1" threadId="t1" />)
    expect(capture.lastMentionableArg).toEqual({ collaboratorIds: new Set(["u1"]) })
  })

  test("submit forwards the claim id + unfurl flag to useCommentSubmit", async () => {
    render(<EmailThreadCommentForm workspaceId="w1" threadId="t1" />)
    await capture.lastComposerProps.onSubmit("hello", "claim-1", false)
    // No reply in flight → reply_to_id is null.
    expect(capture.sendSpy).toHaveBeenCalledWith("hello", "claim-1", false, null)
  })

  test("threads the reply target's id and renders the compose banner while replying", () => {
    const replyingTo = {
      id: "target-c",
      user_name: "Alice",
      content_preview: "the quoted text",
      is_deleted: false,
    }
    const onClearReply = vi.fn()
    render(
      <EmailThreadCommentForm workspaceId="w1" threadId="t1" replyingTo={replyingTo} onClearReply={onClearReply} />
    )
    // The banner shows the target's author + preview above the composer.
    expect(capture.lastComposerProps.replyPreview).toBeTruthy()
    // Submitting sends the target's id as reply_to_id.
    void capture.lastComposerProps.onSubmit("a reply", "claim-9", true)
    expect(capture.sendSpy).toHaveBeenCalledWith("a reply", "claim-9", true, "target-c")
  })

  test("appends the created comment via onSent on success", () => {
    const onSent = vi.fn()
    render(<EmailThreadCommentForm workspaceId="w1" threadId="t1" onSent={onSent} />)
    // useCommentSubmit calls onSuccess (= onSent) with the created comment.
    expect(capture.submitOnSuccess).toBe(onSent)
  })

  test("forwards onEditPrevious and the focus ref to the composer", () => {
    const onEditPrevious = vi.fn(() => true)
    const ref = createRef<CommentComposerFocusHandle>()
    render(<EmailThreadCommentForm ref={ref} workspaceId="w1" threadId="t1" onEditPrevious={onEditPrevious} />)
    expect(capture.lastComposerProps.onEditPrevious).toBe(onEditPrevious)
    // The ref reaches the composer's focus handle.
    ref.current?.focus()
    expect(capture.focusSpy).toHaveBeenCalledOnce()
  })
})
