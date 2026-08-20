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

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => {
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
    accessDeniedUrl: (error: unknown): string | undefined => {
      if (!(error instanceof ApiError) || error.status !== 403) return undefined
      const url = error.body?.request_access_url
      return typeof url === "string" ? url : undefined
    },
  }
})

import { ApiError, apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { DocumentShow } from "../../../../../app/javascript/react/features/documentShow/DocumentShow"
import type { DocumentShowResponse } from "../../../../../app/javascript/react/shared/types"
import { createTestQueryClient } from "../../shared/testUtils"

const mockApiFetch = vi.mocked(apiFetch)

function makeShow(overrides: Partial<DocumentShowResponse> = {}): DocumentShowResponse {
  return {
    id: "doc-1",
    title: "Quarterly Plan",
    sharing: "private",
    creator: { id: "u1", display_name: "Alice", picture: null },
    updated_at: "2026-04-20T09:00:00Z",
    workspace_id: "ws-1",
    is_collaborator: false,
    is_creator: false,
    collaborators: [],
    collaborator_count: 0,
    request_access_url: "/workspaces/ws-1/collaborators/request_access",
    upload_url: "/workspaces/ws-1/attachments",
    ...overrides,
  }
}

// Routes apiFetch: the detail + content endpoints back the page; the visit POST
// is fire-and-forget, so any other call resolves harmlessly.
function routeApiFetch({ show, markdown = "Hello body" }: { show: DocumentShowResponse; markdown?: string }) {
  mockApiFetch.mockImplementation(async (url: string) => {
    if (url === "/api/documents/doc-1") return show
    if (url === "/api/documents/doc-1/content") return { markdown }
    return {}
  })
}

async function renderShow(initialEntry = "/documents/doc-1?return_to=%2Fdocuments") {
  const rootRoute = createRootRoute()
  const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })
  const documentsTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/documents",
    component: () => <div data-testid="index-page" />,
  })
  const documentShowTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/documents/$documentId",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
    }),
    component: DocumentShow,
  })
  // The collaborator redirect is a typed client navigation, so the editor needs
  // a real destination in the tree to land on (a stub reflecting its
  // params/search, not the heavy editor island).
  const documentEditTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/documents/$documentId/edit",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
    }),
    component: function EditStub() {
      const { documentId } = documentEditTestRoute.useParams()
      const { return_to } = documentEditTestRoute.useSearch()
      return <div data-testid="edit-page" data-document-id={documentId} data-return-to={return_to ?? ""} />
    },
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      shellTestRoute.addChildren([documentsTestRoute, documentShowTestRoute, documentEditTestRoute]),
    ]),
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
  return utils
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("DocumentShow", () => {
  test("offers a request-access affordance when the API denies access (403)", async () => {
    const denied = new ApiError(403, { request_access_url: "/workspaces/ws-1/collaborators/access" })
    mockApiFetch.mockRejectedValue(denied)

    await renderShow()

    const link = await screen.findByTestId("request-document-access")
    expect(link.getAttribute("href")).toBe("/workspaces/ws-1/collaborators/access")
    // Not the generic dead-end error.
    expect(screen.queryByText("Could not load this document.")).toBeNull()
  })

  test("renders the read-only view for a non-collaborator", async () => {
    routeApiFetch({ show: makeShow(), markdown: "Hello body" })

    await renderShow()

    expect(await screen.findByText("Quarterly Plan")).toBeTruthy()
    expect(screen.getByText("Hello body")).toBeTruthy()
    expect(screen.getByText("Back to documents")).toBeTruthy()
    // A non-collaborator stays on the read-only show page; no editor redirect.
    expect(screen.queryByTestId("edit-page")).toBeNull()
  })

  test("ignores an off-site return_to (no open redirect on the back link)", async () => {
    routeApiFetch({ show: makeShow() })

    await renderShow("/documents/doc-1?return_to=https%3A%2F%2Fevil.com%2Fphish")

    const back = await screen.findByText("Back to documents")
    // The back link falls back to the safe default, never the attacker URL.
    expect(back.closest("a")?.getAttribute("href")).not.toContain("evil.com")
    expect(screen.queryByRole("link", { name: /evil\.com/ })).toBeNull()
  })

  test("labels the back link generically for an unknown same-origin return_to", async () => {
    routeApiFetch({ show: makeShow() })

    await renderShow("/documents/doc-1?return_to=%2Fwhatever")

    expect(await screen.findByText("Back")).toBeTruthy()
    expect(screen.queryByText("Back to documents")).toBeNull()
  })

  test("redirects a collaborator to the editor, preserving return_to", async () => {
    routeApiFetch({ show: makeShow({ is_collaborator: true }) })

    await renderShow()

    const edit = await screen.findByTestId("edit-page")
    expect(edit.getAttribute("data-document-id")).toBe("doc-1")
    expect(edit.getAttribute("data-return-to")).toBe("/documents")
    // The read-only content never flashes during the redirect.
    expect(screen.queryByText("Quarterly Plan")).toBeNull()
  })

  test("does not forward an off-site return_to into the collaborator redirect", async () => {
    routeApiFetch({ show: makeShow({ is_collaborator: true }) })

    await renderShow("/documents/doc-1?return_to=https%3A%2F%2Fevil.com%2Fphish")

    // The redirect drops the unsafe return_to rather than carrying it to the editor.
    const edit = await screen.findByTestId("edit-page")
    expect(edit.getAttribute("data-return-to")).toBe("")
  })
})
