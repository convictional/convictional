import { cleanup, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// Regression guard: posts have no collaborator concept in the UI, so their
// comment composers must request mentions ORG-WIDE — i.e. call
// useMentionableUsers without collaboratorIds. Passing collaboratorIds would
// re-introduce the "Collaborators" section split in the mention dropdown.
const mentionableSpy = vi.fn(() => [])
vi.mock("~/react/shared/hooks/useMentionableUsers", () => ({
  useMentionableUsers: (opts?: unknown) => mentionableSpy(opts),
}))

// The edit editor scopes on workspaceId when collaborators are requested; posts
// pass null, so this returns undefined either way here.
vi.mock("~/react/shared/hooks/useWorkspaceCollaboratorIds", () => ({
  useWorkspaceCollaboratorIds: () => undefined,
}))

// Stub the heavy composer/editor — we only care about how mentions are sourced.
vi.mock("~/react/composites/comment/CommentComposer", () => ({
  CommentComposer: () => <div data-testid="comment-composer" />,
}))
vi.mock("~/react/composites/chat/ChatComposerEditor", () => ({
  ChatComposerEditor: () => <div data-testid="chat-composer" />,
}))
vi.mock("~/react/composites/editor/components/GifPicker", () => ({
  GifPicker: () => <div data-testid="gif-picker" />,
}))

vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ user: { id: "me", display_name: "Me", picture: null }, clientConfig: null }),
}))
vi.mock("~/react/shared/hooks/useIsMobile", () => ({ useIsMobile: () => false }))

import { CommentEditor } from "~/react/composites/comment/CommentEditor"
import { AddCommentBar } from "~/react/features/postShow/components/AddCommentBar"
import { ReplyComposer } from "~/react/features/postShow/components/ReplyComposer"

beforeEach(() => mentionableSpy.mockClear())
afterEach(cleanup)

function lastCollaboratorIdsArg() {
  const opts = mentionableSpy.mock.calls.at(-1)?.[0] as { collaboratorIds?: unknown } | undefined
  return opts?.collaboratorIds
}

describe("post comment composers source mentions org-wide", () => {
  test("AddCommentBar does not scope mentions to collaborators", () => {
    render(<AddCommentBar workspaceId="ws-1" onSubmit={vi.fn()} onSent={vi.fn()} />)
    expect(mentionableSpy).toHaveBeenCalled()
    expect(lastCollaboratorIdsArg()).toBeUndefined()
  })

  test("ReplyComposer does not scope mentions to collaborators", () => {
    render(<ReplyComposer workspaceId="ws-1" onSubmit={vi.fn()} />)
    expect(mentionableSpy).toHaveBeenCalled()
    expect(lastCollaboratorIdsArg()).toBeUndefined()
  })

  test("CommentEditor (post) does not scope mentions to collaborators", () => {
    render(<CommentEditor initialContent="" workspaceId="ws-1" onSave={vi.fn()} onCancel={vi.fn()} />)
    expect(mentionableSpy).toHaveBeenCalled()
    expect(lastCollaboratorIdsArg()).toBeUndefined()
  })
})
