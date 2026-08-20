import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import type { EmailThreadComment } from "~/react/shared/types"

// EmailThreadCommentEditor is a thin wrapper over the shared CommentEditor; stub
// it to capture the props the wrapper threads down.
const capture = vi.hoisted(() => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  lastProps: null as any,
}))

vi.mock("~/react/composites/comment/CommentEditor", () => ({
  CommentEditor: (props: Record<string, unknown>) => {
    capture.lastProps = props
    return <div data-testid="comment-editor" />
  },
}))

import { EmailThreadCommentEditor } from "~/react/features/emailThreadShow/components/EmailThreadCommentEditor"

const comment = { id: "c1", content: "hello **world**" } as EmailThreadComment

afterEach(() => {
  cleanup()
  capture.lastProps = null
})

describe("EmailThreadCommentEditor", () => {
  test("renders the shared editor seeded with the comment and collaborator-scoped mentions", () => {
    const onSave = vi.fn()
    const onCancel = vi.fn()
    render(<EmailThreadCommentEditor comment={comment} workspaceId="w1" onSave={onSave} onCancel={onCancel} />)

    expect(screen.getByTestId("comment-editor")).toBeInTheDocument()
    expect(capture.lastProps.initialContent).toBe("hello **world**")
    expect(capture.lastProps.workspaceId).toBe("w1")
    expect(capture.lastProps.onSave).toBe(onSave)
    expect(capture.lastProps.onCancel).toBe(onCancel)
    // Email threads expose collaborators, so mentions stay collaborator-split.
    expect(capture.lastProps.scopeMentionsToCollaborators).toBe(true)
  })
})
