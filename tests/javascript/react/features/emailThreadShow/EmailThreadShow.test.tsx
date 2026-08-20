import { QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { act, cleanup, render as rtlRender, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => {
  class ApiError extends Error {
    status: number
    body: Record<string, unknown> | null
    constructor(status: number, body: Record<string, unknown> | null = null) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = body
    }
  }
  return {
    apiFetch: vi.fn(),
    ApiError,
    // Mirrors the real pure helper: pull request_access_url out of a 403.
    accessDeniedUrl: (error: unknown) => {
      if (!(error instanceof ApiError) || error.status !== 403) return undefined
      const url = error.body?.request_access_url
      return typeof url === "string" ? url : undefined
    },
  }
})

// The loaded tree is out of scope for these route-level tests; stub the heavy
// children so a resolved envelope renders cheaply. EmailThreadTitle echoes the
// title so we can tell which thread is showing.
// No channel-backed live updates here; resolve the hook to the null it would
// return anyway, without the "not available at mount" warning.
vi.mock("~/react/shared/hooks/useChannelsClient", () => ({ useChannelsClient: () => null }))
vi.mock("~/react/features/emailThreadShow/components/EmailThreadHeader", () => ({
  EmailThreadHeader: () => null,
}))
vi.mock("~/react/features/emailThreadShow/components/Timeline", () => ({
  Timeline: () => <div data-testid="timeline" />,
}))
vi.mock("~/react/features/emailThreadShow/components/EmailThreadCommentForm", () => ({
  EmailThreadCommentForm: () => null,
}))
vi.mock("~/react/features/emailThreadShow/components/EmailThreadTitle", () => ({
  EmailThreadTitle: ({ thread }: { thread: { title: string } }) => (
    <h1 data-testid="thread-title">{thread.title}</h1>
  ),
}))

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { EmailThreadShow } from "~/react/features/emailThreadShow/EmailThreadShow"
import type { EmailThreadShowResponse } from "~/react/shared/types"
import { createTestQueryClient } from "../../shared/testUtils"

const mockApiFetch = vi.mocked(apiFetch)

function makeEnvelope(threadId: string, title: string): EmailThreadShowResponse {
  return {
    thread: {
      id: threadId,
      title,
      workspace_id: `ws-${threadId}`,
      creator: { id: "creator-1", display_name: "Creator" },
      can_reply: true,
      is_shared: false,
      own_thread_id: null,
    },
    mailbox_entry: {
      id: `entry-${threadId}`,
      is_unread: false,
      is_archived: false,
      is_snoozed: false,
      snoozed_until: null,
      is_ai_excluded: false,
      is_shared: false,
      read_at: "2026-01-01T00:00:00Z",
    },
    timeline: [],
    comments: [],
    draft: null,
    last_event_id: null,
  }
}

async function renderShow(initialEntry: string) {
  const rootRoute = createRootRoute()
  const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })
  const threadShowTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/email_threads/$emailThreadId",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
      mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
    }),
    // Mirrors the production route: remount on emailThreadId so a neighbor-thread
    // navigation reinitializes per-thread state rather than latching the prior thread.
    remountDeps: ({ params }: { params: { emailThreadId: string } }) => params.emailThreadId,
    component: EmailThreadShow,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([shellTestRoute.addChildren([threadShowTestRoute])]),
    history: createMemoryHistory({ initialEntries: [initialEntry] }),
  })
  const utils = rtlRender(
    <QueryClientProvider client={createTestQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  await act(async () => {
    await router.load()
  })
  return { router, ...utils }
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("EmailThreadShow", () => {
  test("shows the skeleton before the envelope resolves", async () => {
    mockApiFetch.mockImplementation(async (url: string) => {
      if (url.startsWith("/api/email_threads/")) return new Promise(() => {}) // never resolves
      return {}
    })

    await renderShow("/email_threads/t1")

    expect(screen.getByTestId("email-thread-skeleton")).toBeTruthy()
  })

  test("offers a request-access CTA when the API denies access (403)", async () => {
    mockApiFetch.mockImplementation(async (url: string) => {
      if (url === "/api/email_threads/t1") {
        throw new ApiError(403, { request_access_url: "/workspaces/ws-1/collaborators/access" })
      }
      return {}
    })

    await renderShow("/email_threads/t1")

    const link = await screen.findByTestId("request-document-access")
    expect(link.getAttribute("href")).toBe("/workspaces/ws-1/collaborators/access")
    expect(screen.getByText(/don.t have access to this thread/i)).toBeTruthy()
    // Not the generic dead-end error.
    expect(screen.queryByText(/Couldn't load this thread/i)).toBeNull()
  })

  test("resets per-thread state when navigating to a neighbor thread", async () => {
    mockApiFetch.mockImplementation(async (url: string) => {
      if (url === "/api/email_threads/a") return makeEnvelope("a", "Thread A")
      if (url === "/api/email_threads/b") return new Promise(() => {}) // hold B pending
      if (url.includes("/decisions")) return { decisions: [] }
      return {}
    })

    const { router } = await renderShow("/email_threads/a")

    expect(await screen.findByText("Thread A")).toBeTruthy()

    await act(async () => {
      await router.navigate({ to: "/email_threads/$emailThreadId", params: { emailThreadId: "b" } })
    })

    // B's envelope is still pending, so the skeleton shows and A's content is
    // gone — the prior thread never flashes through.
    expect(screen.getByTestId("email-thread-skeleton")).toBeTruthy()
    expect(screen.queryByText("Thread A")).toBeNull()
  })
})
