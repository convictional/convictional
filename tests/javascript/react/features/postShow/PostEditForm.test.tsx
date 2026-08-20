import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { cleanup, fireEvent, render, screen, waitFor } from "../../shared/testUtils"
import { resetOrganizationMembers } from "../../shared/organizationMembersFixtures"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

// Stub the ProseMirror-backed editor with a ref handle returning fixed content.
// This guards the regression where PostEditForm rendered the editor without
// `ref={editorRef}`, so getContent() was never reachable and the body went up
// empty (422). React is loaded inside the factory to stay clear of vi.mock hoisting.
vi.mock("~/react/composites/editor/RichTextComposer", async () => {
  const React = await vi.importActual<typeof import("react")>("react")
  return {
    RichTextComposer: React.forwardRef((_props, ref) => {
      React.useImperativeHandle(ref, () => ({
        getContent: () => "edited body content",
        isEmpty: () => false,
        insertImage: () => {},
        attachmentClaimId: "claim-123",
      }))
      return React.createElement("div", { "data-testid": "post-body-editor" })
    }),
  }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { PostEditForm } from "~/react/features/postShow/components/PostEditForm"

import { buildPostDetail } from "./fixtures"

const mockedFetch = vi.mocked(apiFetch)

function patchCall() {
  return mockedFetch.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PATCH")
}

beforeEach(() => {
  mockedFetch.mockReset()
  // /api/organization/members lookup on mount; PATCH on save.
  mockedFetch.mockImplementation((_url: string, init?: RequestInit) =>
    init?.method === "PATCH"
      ? Promise.resolve(buildPostDetail({ title: "New title" }))
      : Promise.resolve({ groups: [], users: [] })
  )
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  // The org-members lookup caches in the singleton; clear it so it doesn't leak.
  resetOrganizationMembers()
})

describe("PostEditForm", () => {
  test("Save sends the edited title and serialized body to PATCH", async () => {
    const onSave = vi.fn()
    render(<PostEditForm post={buildPostDetail()} initialContent="old body" onSave={onSave} onCancel={vi.fn()} />)

    fireEvent.change(screen.getByLabelText("Post title"), { target: { value: "New title" } })
    fireEvent.click(screen.getByText("Save changes"))

    await waitFor(() => expect(patchCall()).toBeDefined())
    expect(patchCall()?.[0]).toBe("/api/posts/post-1")
    const body = JSON.parse((patchCall()?.[1] as RequestInit).body as string)
    expect(body.title).toBe("New title")
    // The editor's content must actually reach the request — a non-empty body is
    // what the missing-ref regression broke (it sent "" → 422).
    expect(body.content).toBe("edited body content")
    expect(body.attachment_claim_id).toBe("claim-123")
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.anything(), "edited body content"))
  })

  test("Cancel does not PATCH", () => {
    const onCancel = vi.fn()
    render(<PostEditForm post={buildPostDetail()} initialContent="old body" onSave={vi.fn()} onCancel={onCancel} />)
    fireEvent.click(screen.getByText("Cancel"))
    expect(onCancel).toHaveBeenCalled()
    expect(patchCall()).toBeUndefined()
  })
})
