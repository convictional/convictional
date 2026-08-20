import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))
vi.mock("~/react/composites/confirmationDialog/confirm", () => ({ confirm: vi.fn() }))
// These composites fetch/subscribe on mount; we only care about the header's own
// behavior, so stub them to inert markers.
vi.mock("~/react/composites/MailboxActionBar", () => ({
  MailboxActionBar: () => <div data-testid="mailbox-action-bar" />,
}))
vi.mock("~/react/composites/workspaceCollaborators/WorkspaceCollaborators", () => ({
  WorkspaceCollaborators: () => <div data-testid="collaborators" />,
}))

import { apiFetch } from "~/react/shared/apiFetch"
import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { showFlash } from "~/shared/flash"
import { PostDraftEditorHeader } from "~/react/features/postDraftEditor/PostDraftEditorHeader"
import type { PostDraftMetadata } from "~/react/features/postDraftEditor/types"

const mockedFetch = vi.mocked(apiFetch)
const mockedConfirm = vi.mocked(confirm)

function buildMetadata(overrides: Partial<PostDraftMetadata> = {}): PostDraftMetadata {
  return {
    id: "post-1",
    title: "My Draft",
    group: null,
    is_announcement: false,
    can_announce: true,
    is_creator: true,
    can_delete: true,
    workspace_id: "ws-1",
    org_groups: [{ id: "g1", name: "Engineering" }],
    ...overrides,
  }
}

function renderHeader(props: Partial<Parameters<typeof PostDraftEditorHeader>[0]> = {}) {
  const onMetadataChange = vi.fn()
  const onPublish = vi.fn()
  render(
    <PostDraftEditorHeader
      postId="post-1"
      back={{ url: "/posts", label: "Posts" }}
      mailboxEntry={null}
      metadata={buildMetadata()}
      onMetadataChange={onMetadataChange}
      savingTitle={false}
      titleEverChanged={false}
      publishing={false}
      onPublish={onPublish}
      {...props}
    />
  )
  return { onMetadataChange, onPublish }
}

beforeEach(() => {
  mockedFetch.mockReset()
  mockedFetch.mockResolvedValue({})
  mockedConfirm.mockReset()
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("PostDraftEditorHeader", () => {
  test("selecting a group PATCHes the draft and updates optimistically", async () => {
    const { onMetadataChange } = renderHeader()

    fireEvent.click(screen.getByRole("button", { name: /Everyone/ }))
    fireEvent.click(screen.getByText("Engineering"))

    await waitFor(() => expect(mockedFetch).toHaveBeenCalled())
    const [url, init] = mockedFetch.mock.calls[0]
    expect(url).toBe("/api/posts/post-1/draft")
    expect((init as RequestInit).method).toBe("PATCH")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ group_id: "g1", is_announcement: false })
    expect(onMetadataChange).toHaveBeenCalledWith(expect.objectContaining({ group: { id: "g1", name: "Engineering" } }))
  })

  test("a failed audience change rolls back and flashes", async () => {
    mockedFetch.mockRejectedValueOnce(new Error("boom"))
    const previous = buildMetadata()
    const onMetadataChange = vi.fn()
    render(
      <PostDraftEditorHeader
        postId="post-1"
        back={{ url: "/posts", label: "Posts" }}
        mailboxEntry={null}
        metadata={previous}
        onMetadataChange={onMetadataChange}
        savingTitle={false}
        titleEverChanged={false}
        publishing={false}
        onPublish={vi.fn()}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: /Everyone/ }))
    fireEvent.click(screen.getByText("Engineering"))

    await waitFor(() => expect(showFlash).toHaveBeenCalled())
    // optimistic update, then rollback to the previous metadata
    expect(onMetadataChange).toHaveBeenLastCalledWith(previous)
  })

  test("publish button invokes onPublish", () => {
    const { onPublish } = renderHeader()
    fireEvent.click(screen.getByRole("button", { name: "Post" }))
    expect(onPublish).toHaveBeenCalled()
  })

  test("delete confirms then issues a DELETE", async () => {
    mockedConfirm.mockResolvedValue(true)
    // jsdom can't perform real navigation. The delete redirect goes through
    // boostedNavigate, which sets location.href when htmx is absent (as here),
    // so stub location with an href setter spy to capture the redirect.
    const originalLocation = window.location
    const hrefMock = vi.fn()
    Object.defineProperty(window, "location", {
      value: Object.defineProperty({ search: "", pathname: "/posts", origin: "http://localhost" }, "href", {
        set: hrefMock,
        configurable: true,
      }),
      writable: true,
      configurable: true,
    })

    renderHeader()

    fireEvent.click(screen.getByRole("button", { name: "Delete" }))

    await waitFor(() => expect(mockedConfirm).toHaveBeenCalled())
    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledWith("/api/posts/post-1", expect.objectContaining({ method: "DELETE" }))
    )
    await waitFor(() => expect(hrefMock).toHaveBeenCalledWith("/posts"))

    Object.defineProperty(window, "location", {
      value: originalLocation,
      writable: true,
      configurable: true,
    })
  })

  test("non-creator without admin sees no audience picker and no delete", () => {
    renderHeader({ metadata: buildMetadata({ is_creator: false, can_announce: false, can_delete: false }) })
    expect(screen.queryByRole("button", { name: /Everyone/ })).toBeNull()
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull()
    // publishing stays available to any collaborator
    expect(screen.getByRole("button", { name: "Post" })).toBeTruthy()
  })

  test("search filters the group list", () => {
    renderHeader({
      metadata: buildMetadata({
        org_groups: [
          { id: "g1", name: "Engineering" },
          { id: "g2", name: "Design" },
        ],
      }),
    })

    fireEvent.click(screen.getByRole("button", { name: /Everyone/ }))
    expect(screen.getByText("Engineering")).toBeInTheDocument()
    expect(screen.getByText("Design")).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText("Search groups…"), { target: { value: "eng" } })
    expect(screen.getByText("Engineering")).toBeInTheDocument()
    expect(screen.queryByText("Design")).toBeNull()
  })
})
