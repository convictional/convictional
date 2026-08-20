import { beforeEach, describe, expect, it, vi } from "vitest"

// Keep the real ApiError (the component branches on `instanceof ApiError`); mock
// only the fetch.
vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})
vi.mock("~/react/shared/hooks/useCurrentUser", () => ({ useCurrentUser: vi.fn() }))
vi.mock("~/react/shared/hooks/useVisitRecording", () => ({ useWorkspaceVisitRecording: () => vi.fn() }))
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))
// The header/body pull in the collaborative editor, channels, and collaborator
// fetches — out of scope here. Stub them so the test exercises only the
// container's fetch → redirect/error/render state machine.
vi.mock("~/react/features/postDraftEditor/PostDraftEditorBody", () => ({
  PostDraftEditorBody: () => <div data-testid="editor-body" />,
}))
vi.mock("~/react/features/postDraftEditor/PostDraftEditorHeader", () => ({
  PostDraftEditorHeader: () => <div data-testid="editor-header" />,
}))

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"

import { PostDraftEditor } from "~/react/features/postDraftEditor/PostDraftEditor"

import { screen, waitFor } from "../../shared/testUtils"
import { renderInEditorRouter } from "./harness"

const mockApiFetch = vi.mocked(apiFetch)
const mockUseCurrentUser = vi.mocked(useCurrentUser)

const metadata = {
  id: "p1",
  title: "My Draft",
  group: null,
  is_announcement: false,
  can_announce: false,
  is_creator: true,
  can_delete: true,
  workspace_id: "ws-1",
  org_groups: [],
  upload_url: "/api/workspaces/ws-1/attachments",
  mailbox_entry: null,
}

beforeEach(() => {
  mockApiFetch.mockReset()
  mockUseCurrentUser.mockReturnValue({
    user: { id: "u1", display_name: "Ada", picture: null },
    clientConfig: { klipy_api_key: null },
    loading: false,
    error: null,
  } as unknown as ReturnType<typeof useCurrentUser>)
})

describe("PostDraftEditor", () => {
  it("renders the editor once the draft loads", async () => {
    mockApiFetch.mockImplementation((url: string) =>
      url.startsWith("/api/posts/p1/draft") ? Promise.resolve(metadata) : Promise.reject(new ApiError(404, null))
    )

    await renderInEditorRouter(PostDraftEditor)

    expect(await screen.findByTestId("editor-body")).toBeInTheDocument()
    expect(screen.queryByTestId("show-page")).not.toBeInTheDocument()
  })

  it("redirects a published post to the read-only show page", async () => {
    // The draft endpoint 404s a published post; the show endpoint confirms it
    // exists, so the editor redirects there rather than erroring.
    mockApiFetch.mockImplementation((url: string) =>
      url.startsWith("/api/posts/p1/draft")
        ? Promise.reject(new ApiError(404, null))
        : Promise.resolve({ post: {} })
    )

    const { router } = await renderInEditorRouter(PostDraftEditor)

    expect(await screen.findByTestId("show-page")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/posts/p1")
  })

  it("shows an error (no redirect loop) when the post genuinely does not exist", async () => {
    // Both endpoints 404 → the post is nonexistent/inaccessible. The editor must
    // land on its error state, not bounce back to show (which would ping-pong).
    mockApiFetch.mockImplementation(() => Promise.reject(new ApiError(404, null)))

    const { router } = await renderInEditorRouter(PostDraftEditor)

    expect(await screen.findByText("Could not load this draft.")).toBeInTheDocument()
    expect(screen.queryByTestId("show-page")).not.toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/posts/p1/edit")
  })
})
