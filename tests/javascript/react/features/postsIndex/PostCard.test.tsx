import { act, cleanup, fireEvent, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

import { PostCard } from "~/react/features/postsIndex/components/PostCard"
import type { Post } from "~/react/shared/types"
import type { PostListDecision } from "~/react/features/postsIndex/types"

import { makePost, makeUser } from "./fixtures"
import { renderInPostsRouter } from "./harness"

// PostCard renders a typed <Link>, so it must mount inside the router as the index
// route's component. returnTo is the index URL the card stamps onto the show link.
function renderCard(post: Post, decision: PostListDecision | null = null) {
  return renderInPostsRouter(() => <PostCard post={post} decision={decision} returnTo="/posts" />)
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiFetchMock.mockReturnValue(new Promise(() => {}))
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("PostCard", () => {
  test("hovering a participant avatar opens the profile card", async () => {
    const { container } = await renderCard(makePost({ comment_count: 1, participants: [makeUser({ id: "p-user" })] }))

    vi.useFakeTimers()
    // Stack layout renders the UserHoverCard trigger <span> directly under .avatar-group.
    const trigger = container.querySelector(".avatar-group > span")!
    fireEvent.mouseEnter(trigger)
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    expect(apiFetchMock).toHaveBeenCalledWith("/api/people/p-user")
    expect(apiFetchMock).toHaveBeenCalledWith("/api/users/p-user/top_goal?expand=parent")
  })

  test("renders title, author, group, and content preview", async () => {
    await renderCard(
      makePost({
        title: "Quarterly plan",
        creator: makeUser({ display_name: "Alice" }),
        group: { id: "g1", name: "Eng" },
        content_preview: "Here is the plan body.",
      })
    )
    expect(screen.getByText("Quarterly plan")).toBeInTheDocument()
    expect(screen.getByText("@Alice")).toBeInTheDocument()
    expect(screen.getByText("@Eng")).toBeInTheDocument()
    expect(screen.getByText("Here is the plan body.")).toBeInTheDocument()
  })

  test("links to the post show page with a return_to param", async () => {
    await renderCard(makePost({ id: "abc" }))
    const link = screen.getByRole("link")
    const href = link.getAttribute("href") ?? ""
    expect(href).toContain("/posts/abc")
    expect(href).toContain("return_to=%2Fposts")
  })

  test("renders the link preview when present", async () => {
    await renderCard(
      makePost({
        link_preview: {
          url: "https://example.com/article",
          title: "An article",
          description: "A description",
          image_url: null,
        },
      })
    )
    expect(screen.getByText("An article")).toBeInTheDocument()
    expect(screen.getByText("A description")).toBeInTheDocument()
    expect(screen.getByText("example.com")).toBeInTheDocument()
  })

  test("renders the decision row with a truncated preview for a single decision", async () => {
    await renderCard(makePost({ id: "p1" }), { post_id: "p1", count: 1, comment_preview: "We will ship on Friday." })
    expect(screen.getByText("Decision")).toBeInTheDocument()
    expect(screen.getByText("We will ship on Friday.")).toBeInTheDocument()
  })

  test("shows a decision count instead of a preview when there are multiple", async () => {
    await renderCard(makePost({ id: "p1" }), { post_id: "p1", count: 3, comment_preview: "We will ship on Friday." })
    expect(screen.getByText("3 Decisions")).toBeInTheDocument()
    expect(screen.queryByText("Decision")).not.toBeInTheDocument()
    expect(screen.queryByText("We will ship on Friday.")).not.toBeInTheDocument()
  })

  test("shows the '{n} new' badge when there are new comments", async () => {
    await renderCard(makePost({ comment_count: 5, new_comment_count: 2 }))
    expect(screen.getByText(/5 · 2 new/)).toBeInTheDocument()
  })

  test("shows a plain comment count when nothing is new", async () => {
    await renderCard(makePost({ comment_count: 3, new_comment_count: 0 }))
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.queryByText(/new/)).not.toBeInTheDocument()
  })

  test("renders participant avatars only when comment_count > 0", async () => {
    const participants = [makeUser({ id: "u1", display_name: "Bob" })]

    const { container: noComments } = await renderCard(makePost({ comment_count: 0, participants }))
    expect(noComments.querySelector(".avatar")).toBeNull()
    cleanup()

    const { container: withComments } = await renderCard(makePost({ comment_count: 1, participants }))
    expect(withComments.querySelector(".avatar")).not.toBeNull()
  })
})
