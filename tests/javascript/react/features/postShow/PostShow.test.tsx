import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { act, cleanup, render as rtlRender, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: Record<string, unknown> | null
    constructor(status: number, body: Record<string, unknown> | null = null) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = body
    }
  },
}))

// The post island subscribes to channels for live comments/decisions; that path is
// covered by the hook tests, so stub it out here to keep this a focused mount test.
vi.mock("~/react/shared/hooks/useChannel", () => ({ useChannel: () => {} }))
vi.mock("~/channels/client", () => ({ getChannelsClient: () => null }))

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { PostShow } from "~/react/features/postShow/PostShow"
import { postQueryKey } from "~/react/features/postShow/queries"
import type { PostShowResponse } from "~/react/shared/types"

import { buildCurrentUserApiResponse } from "../../shared/currentUserFixtures"
import { createTestQueryClient } from "../../shared/testUtils"
import { buildComment, buildShowResponse, buildUser } from "./fixtures"

const POST_ID = "post-1"
const WS_ID = "ws-1"
const VIEWER_ID = "viewer"

const mockApiFetch = vi.mocked(apiFetch)

// Routes apiFetch by URL. The detail + comments + decisions endpoints back the
// page; the visit POST, subscription, views, and /api/users/me calls resolve
// harmlessly. Comments echoes back exactly the comments the show response bundled
// so the mount fetch doesn't wipe the seeded list.
function routeApiFetch({ show, detailReject }: { show: PostShowResponse; detailReject?: unknown }) {
  const comments = show.original_comment
    ? [...show.top_level_comments, show.original_comment]
    : [...show.top_level_comments]
  mockApiFetch.mockImplementation(async (url: string) => {
    const path = url.split("?")[0]
    if (path === `/api/posts/${POST_ID}`) {
      if (detailReject) throw detailReject
      return show
    }
    if (path === `/api/posts/${POST_ID}/comments`) return { comments, next_cursor: null, has_more: false }
    if (path === `/api/workspaces/${WS_ID}/decisions`) return { decisions: [], next_cursor: null, has_more: false }
    if (path === "/api/users/me") return buildCurrentUserApiResponse({ id: VIEWER_ID })
    if (path === `/api/posts/${POST_ID}/views`) {
      return { seen_count: 0, total_audience: 0, first_seen_at: null, last_seen_at: null, group: null, views: [] }
    }
    return {}
  })
}

let queryClient: QueryClient

async function renderShow(initialEntry = `/posts/${POST_ID}?return_to=%2Fposts`) {
  queryClient = createTestQueryClient()
  const rootRoute = createRootRoute()
  const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })
  const postShowTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/posts/$postId",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
      mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
    }),
    component: PostShow,
  })
  // Stub the draft editor route so the draft→edit client redirect has a target to
  // land on (the real editor is its own island, out of scope for this mount test).
  const postDraftEditorTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/posts/$postId/edit",
    validateSearch: (search: Record<string, unknown>) => search,
    component: () => <p>Draft editor</p>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      shellTestRoute.addChildren([postShowTestRoute, postDraftEditorTestRoute]),
    ]),
    history: createMemoryHistory({ initialEntries: [initialEntry] }),
  })
  const utils = rtlRender(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  await act(async () => {
    await router.load()
  })
  return utils
}

// Panel-unique text: the "{n} new since <relative time>" header lives only in the
// what's-new panel (the comment previews it shows also appear in the thread).
const whatsNewPanel = () => screen.queryByText(/new since/i)

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("PostShow", () => {
  test("swaps the skeleton for the post once the detail query resolves", async () => {
    routeApiFetch({ show: buildShowResponse() })

    await renderShow()

    // The title only renders once PostBody has data; the skeleton has no such text.
    expect(await screen.findByText("A post")).toBeTruthy()
    expect(screen.getByText("Post body")).toBeTruthy()
  })

  test("redirects a draft (404 at the show endpoint) to the editor without flashing the error card", async () => {
    routeApiFetch({ show: buildShowResponse(), detailReject: new ApiError(404, null) })

    await renderShow(`/posts/${POST_ID}?return_to=%2Fposts`)

    // The 404 client-routes to the draft editor (stubbed in the harness).
    await waitFor(() => expect(screen.getByText("Draft editor")).toBeTruthy())
    // The error card is held behind the skeleton during the redirect.
    expect(screen.queryByText("Couldn't load this post. Please refresh.")).toBeNull()
  })

  test("keeps what's-new frozen against the first-load last_visit_at when the detail refetches newer", async () => {
    const show = buildShowResponse({
      last_visit_at: "2026-05-01T00:00:00Z",
      top_level_comments: [
        buildComment({
          id: "c-new",
          global_id: "gid://convictional/PostComment/c-new",
          content: "Fresh news",
          created_at: "2026-06-01T00:00:00Z",
          user: buildUser({ id: "user-2", display_name: "Bob" }),
        }),
      ],
    })
    routeApiFetch({ show })

    await renderShow()

    // The comment postdates the frozen last_visit_at, so the panel surfaces it.
    expect(await screen.findByText(/new since/i)).toBeTruthy()

    // Simulate a detail refetch returning a last_visit_at AFTER the comment. With
    // the freeze this must NOT empty the panel; without it, what's-new collapses.
    act(() => {
      queryClient.setQueryData<PostShowResponse>(postQueryKey(POST_ID), old =>
        old ? { ...old, last_visit_at: "2026-07-01T00:00:00Z" } : old
      )
    })

    await waitFor(() => expect(whatsNewPanel()).not.toBeNull())
    expect(whatsNewPanel()).not.toBeNull()
  })
})
