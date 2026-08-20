import { act, cleanup, fireEvent, render, screen } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

// Stub the edit form (ProseMirror) and analytics (network) so PostBody's own
// display/edit-toggle logic is what's under test.
vi.mock("~/react/features/postShow/components/PostEditForm", () => ({
  PostEditForm: () => <div data-testid="post-edit-form" />,
}))
vi.mock("~/react/features/postShow/components/ReadAnalytics", () => ({
  ReadAnalytics: () => null,
}))

import { PostBody } from "~/react/features/postShow/components/PostBody"

import { buildComment, buildPostDetail, buildUser } from "./fixtures"

function renderBody(props: Partial<Parameters<typeof PostBody>[0]> = {}) {
  return render(
    <PostBody
      post={buildPostDetail()}
      originalComment={buildComment({ id: "orig", content: "The body" })}
      decisions={[]}
      decisionsByGid={new Map()}
      toggleDecision={vi.fn()}
      currentUserId="viewer"
      registerRef={() => () => {}}
      onSave={vi.fn()}
      onToggleReaction={vi.fn()}
      onJumpToDecision={vi.fn()}
      {...props}
    />
  )
}

beforeEach(() => {
  vi.useFakeTimers()
  apiFetchMock.mockReset()
  apiFetchMock.mockReturnValue(new Promise(() => {}))
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("PostBody", () => {
  test("hovering the post author avatar opens the profile card", async () => {
    renderBody({ originalComment: buildComment({ id: "orig", user: buildUser({ id: "author-1" }) }) })

    const avatar = document.querySelector(".avatar")!
    fireEvent.mouseEnter(avatar.parentElement!)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledWith("/api/people/author-1")
    expect(apiFetchMock).toHaveBeenCalledWith("/api/users/author-1/top_goal?expand=parent")
  })

  test("renders the title and body content", () => {
    renderBody({ post: buildPostDetail({ title: "Launch plan" }) })
    expect(screen.getByText("Launch plan")).toBeInTheDocument()
    expect(screen.getByText("The body")).toBeInTheDocument()
  })

  test("renders pinned and announcement badges", () => {
    renderBody({ post: buildPostDetail({ is_pinned: true, is_announcement: true }) })
    expect(screen.getByText("Pinned")).toBeInTheDocument()
    expect(screen.getByText("Announcement")).toBeInTheDocument()
  })

  test("renders the group tag", () => {
    renderBody({ post: buildPostDetail({ group: { id: "g1", name: "Eng" } }) })
    expect(screen.getByText("@Eng")).toBeInTheDocument()
  })

  test("the overflow Edit flips into the edit form for editors", () => {
    renderBody({ post: buildPostDetail({ permissions: { edit: true, pin: false, delete: true } }) })
    fireEvent.click(screen.getByRole("button", { name: "Post actions" }))
    fireEvent.click(screen.getByText("Edit"))
    expect(screen.getByTestId("post-edit-form")).toBeInTheDocument()
  })

  test("hides the overflow when the viewer cannot edit", () => {
    renderBody({ post: buildPostDetail({ permissions: { edit: false, pin: false, delete: false } }) })
    expect(screen.queryByRole("button", { name: "Post actions" })).not.toBeInTheDocument()
  })

  test("renders the original comment link preview", () => {
    renderBody({
      originalComment: buildComment({
        id: "orig",
        link_preview: { url: "https://example.com", title: "Preview title", description: null, image_url: null },
      }),
    })
    expect(screen.getByText("Preview title")).toBeInTheDocument()
  })
})

describe("PostBody on mobile (long-press action sheet)", () => {
  beforeEach(() => {
    document.documentElement.dataset.isMobile = "true"
  })
  afterEach(() => {
    delete document.documentElement.dataset.isMobile
  })

  function openSheet() {
    // Global beforeEach already installs fake timers; just advance past the
    // long-press threshold.
    fireEvent.touchStart(screen.getByText("The body"))
    act(() => {
      vi.advanceTimersByTime(500)
    })
  }

  test("hides the hover overflow and opens the sheet with reactors + Edit for editors", () => {
    renderBody({
      post: buildPostDetail({ permissions: { edit: true, pin: false, delete: true } }),
      originalComment: buildComment({
        id: "orig",
        content: "The body",
        reactions: { thumbs_up: [{ id: "u2", display_name: "Bob" }] },
      }),
    })
    // The hover overflow is unreachable on touch, so it's not rendered on mobile.
    expect(screen.queryByRole("button", { name: "Post actions" })).not.toBeInTheDocument()

    openSheet()

    expect(screen.getByRole("dialog", { name: "Post actions" })).toBeInTheDocument()
    expect(screen.getByText("Bob")).toBeInTheDocument()
    // Editors get Edit; a post has no inline delete, so no Delete row.
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument()
  })

  test("omits Edit in the sheet for non-editors", () => {
    renderBody({
      post: buildPostDetail({ permissions: { edit: false, pin: false, delete: false } }),
      originalComment: buildComment({ id: "orig", content: "The body" }),
    })
    openSheet()
    expect(screen.getByRole("dialog", { name: "Post actions" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument()
  })
})
