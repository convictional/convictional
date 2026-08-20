import { act, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))

import type { PostDraftListResponse, PostListResponse } from "~/react/features/postsIndex/types"
import { apiFetch } from "~/react/shared/apiFetch"

import { makeDraft, makePost } from "./fixtures"
import { renderPostsDataHook } from "./harness"

const mockApiFetch = vi.mocked(apiFetch)

function makeList(overrides: Partial<PostListResponse> = {}): PostListResponse {
  return { posts: [], decisions: [], draft_count: 0, next_cursor: null, has_more: false, ...overrides }
}

function makeDraftList(overrides: Partial<PostDraftListResponse> = {}): PostDraftListResponse {
  return { drafts: [], next_cursor: null, has_more: false, ...overrides }
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(() => vi.clearAllMocks())

describe("usePostsData", () => {
  test("fetches the published feed and pinned rail on mount", async () => {
    mockApiFetch.mockImplementation(async (url: string) => {
      if (url.includes("pinned=true")) return makeList({ posts: [makePost({ id: "pin" })], draft_count: 4 })
      return makeList({
        posts: [makePost({ id: "a" }), makePost({ id: "b" })],
        draft_count: 4,
        has_more: true,
        next_cursor: "c1",
      })
    })

    const { result } = await renderPostsDataHook()
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.posts.map(p => p.id)).toEqual(["a", "b"])
    expect(result.current.pinnedPosts.map(p => p.id)).toEqual(["pin"])
    expect(result.current.draftCount).toBe(4)
    expect(result.current.hasMore).toBe(true)
    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("pinned=false"), expect.any(Object))
    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("pinned=true"), expect.any(Object))
  })

  test("reads the initial filters from the URL", async () => {
    mockApiFetch.mockResolvedValue(makeList())
    const { result } = await renderPostsDataHook(["/posts?group_id=g1&decided=true"])
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.groupId).toBe("g1")
    expect(result.current.decided).toBe(true)
    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("group_id=g1"), expect.any(Object))
    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("decided=true"), expect.any(Object))
  })

  test("changeGroup resets, refetches with group_id, and syncs the URL", async () => {
    mockApiFetch.mockResolvedValue(makeList())
    const { result, router } = await renderPostsDataHook()
    await waitFor(() => expect(result.current.loading).toBe(false))
    mockApiFetch.mockClear()

    act(() => result.current.changeGroup("g1"))

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("group_id=g1"), expect.any(Object))
    )
    expect(router.state.location.search).toMatchObject({ group_id: "g1" })
  })

  test("toggleDecided refetches with decided=true", async () => {
    mockApiFetch.mockResolvedValue(makeList())
    const { result, router } = await renderPostsDataHook()
    await waitFor(() => expect(result.current.loading).toBe(false))
    mockApiFetch.mockClear()

    act(() => result.current.toggleDecided())

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("decided=true"), expect.any(Object))
    )
    expect(router.state.location.search).toMatchObject({ decided: true })
  })

  test("showDrafts switches to the drafts collection endpoint", async () => {
    mockApiFetch.mockImplementation(async (url: string) => {
      if (url.includes("/api/posts/drafts")) return makeDraftList({ drafts: [makeDraft({ id: "d1" })] })
      return makeList()
    })
    const { result, router } = await renderPostsDataHook()
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.showDrafts())

    await waitFor(() => expect(result.current.drafts.map(d => d.id)).toEqual(["d1"]))
    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("/api/posts/drafts"), expect.any(Object))
    expect(router.state.location.search).toMatchObject({ status: "drafts" })
  })

  test("loadMore appends the next page, deduped by id", async () => {
    mockApiFetch.mockImplementation(async (url: string) => {
      if (url.includes("pinned=true")) return makeList()
      if (url.includes("cursor=")) return makeList({ posts: [makePost({ id: "b" }), makePost({ id: "c" })] })
      return makeList({ posts: [makePost({ id: "a" }), makePost({ id: "b" })], has_more: true, next_cursor: "c1" })
    })

    const { result } = await renderPostsDataHook()
    await waitFor(() => expect(result.current.posts).toHaveLength(2))

    act(() => result.current.loadMore())
    await waitFor(() => expect(result.current.posts.map(p => p.id)).toEqual(["a", "b", "c"]))
  })

  test("prependPost adds a created post to the front without duplicating", async () => {
    mockApiFetch.mockResolvedValue(makeList({ posts: [makePost({ id: "a" })] }))
    const { result } = await renderPostsDataHook()
    await waitFor(() => expect(result.current.posts).toHaveLength(1))

    act(() => result.current.prependPost(makePost({ id: "new" })))
    await waitFor(() => expect(result.current.posts.map(p => p.id)).toEqual(["new", "a"]))

    act(() => result.current.prependPost(makePost({ id: "new" })))
    await waitFor(() => expect(result.current.posts.filter(p => p.id === "new")).toHaveLength(1))
  })

  test("prependPost skips a post that doesn't match the active group filter", async () => {
    mockApiFetch.mockResolvedValue(makeList())
    const { result } = await renderPostsDataHook(["/posts?group_id=g1"])
    // Wait for the empty feed to load, so the prepend patches a cached page.
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.groupId).toBe("g1")

    // Posted to a different group → not shown in the g1-filtered feed.
    act(() => result.current.prependPost(makePost({ id: "other", group: { id: "g2", name: "Other" } })))
    expect(result.current.posts).toHaveLength(0)

    // Posted to the active group → prepended.
    act(() => result.current.prependPost(makePost({ id: "match", group: { id: "g1", name: "Eng" } })))
    await waitFor(() => expect(result.current.posts.map(p => p.id)).toEqual(["match"]))
  })

  test("exposes decisions from both the feed and pinned rail, keyed by post_id", async () => {
    mockApiFetch.mockImplementation(async (url: string) => {
      if (url.includes("pinned=true"))
        return makeList({
          posts: [makePost({ id: "pin" })],
          decisions: [{ post_id: "pin", count: 1, comment_preview: "Pinned call" }],
        })
      return makeList({
        posts: [makePost({ id: "a" })],
        decisions: [{ post_id: "a", count: 1, comment_preview: "Feed call" }],
      })
    })

    const { result } = await renderPostsDataHook()
    await waitFor(() => expect(result.current.loading).toBe(false))
    await waitFor(() => expect(result.current.decisionsByPostId.size).toBe(2))

    expect(result.current.decisionsByPostId.get("a")?.comment_preview).toBe("Feed call")
    expect(result.current.decisionsByPostId.get("pin")?.comment_preview).toBe("Pinned call")
  })

  test("sets error state on fetch failure", async () => {
    mockApiFetch.mockRejectedValue(new Error("boom"))
    const { result } = await renderPostsDataHook()
    await waitFor(() => expect(result.current.error).toBe(true))
  })
})
