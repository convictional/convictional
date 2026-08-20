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

// The body mounts the full Yjs/collaboration stack, which jsdom can't drive. Stub
// it to a marker that reflects the re-sourced props this PR is responsible for.
vi.mock("../../../../../app/javascript/react/features/documentEditor/DocumentEditorBody", () => ({
  DocumentEditorBody: (props: {
    documentId: string
    workspaceId: string
    uploadUrl: string | null
    hasKlipy: boolean
    currentUser: { id: string }
  }) => (
    <div
      data-testid="editor-body"
      data-document-id={props.documentId}
      data-workspace-id={props.workspaceId}
      data-upload-url={props.uploadUrl ?? ""}
      data-has-klipy={String(props.hasKlipy)}
      data-current-user={props.currentUser.id}
    />
  ),
}))

// The header pulls in SubscriptionBell/SharingDropdown/WorkspaceCollaborators,
// none of which this PR changes. Stub it to expose the props the route re-sources.
vi.mock("../../../../../app/javascript/react/features/documentEditor/DocumentEditorHeader", () => ({
  DocumentEditorHeader: (props: {
    back: { url: string; label: string }
    metadata: { title: string } | null
    subscriptionBell: { workspaceId: string; manageUrl?: string }
  }) => (
    <div
      data-testid="editor-header"
      data-back-url={props.back.url}
      data-back-label={props.back.label}
      data-title={props.metadata?.title ?? ""}
      data-bell-workspace={props.subscriptionBell.workspaceId}
      data-bell-manage={props.subscriptionBell.manageUrl ?? ""}
    />
  ),
}))

import { queryClient } from "~/react/shared/queryClient"

import { ApiError, apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { DocumentEditor } from "../../../../../app/javascript/react/features/documentEditor/DocumentEditor"
import type { DocumentShowResponse } from "../../../../../app/javascript/react/shared/types"
import { setCurrentUser } from "../../shared/currentUserFixtures"

const mockApiFetch = vi.mocked(apiFetch)

function makeShow(overrides: Partial<DocumentShowResponse> = {}): DocumentShowResponse {
  return {
    id: "doc-1",
    title: "Quarterly Plan",
    sharing: "private",
    creator: { id: "u1", display_name: "Alice", picture: null },
    updated_at: "2026-04-20T09:00:00Z",
    workspace_id: "ws-1",
    is_collaborator: true,
    is_creator: true,
    collaborators: [],
    collaborator_count: 0,
    request_access_url: "/workspaces/ws-1/collaborators/request_access",
    upload_url: "/workspaces/ws-1/attachments",
    ...overrides,
  }
}

function routeShow(show: DocumentShowResponse) {
  mockApiFetch.mockImplementation(async (url: string) => {
    if (url === "/api/documents/doc-1") return show
    return {}
  })
}

async function renderEditor(initialEntry = "/documents/doc-1/edit?return_to=%2Fdocuments") {
  const rootRoute = createRootRoute()
  const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })
  const documentShowTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/documents/$documentId",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
    }),
    component: function ShowStub() {
      const { return_to } = documentShowTestRoute.useSearch()
      return <div data-testid="show-page" data-return-to={return_to ?? ""} />
    },
  })
  const documentEditTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/documents/$documentId/edit",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
    }),
    component: DocumentEditor,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([shellTestRoute.addChildren([documentShowTestRoute, documentEditTestRoute])]),
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

beforeEach(() => {
  mockApiFetch.mockReset()
  // Seed the viewer the same way every island test does (shared fixture), so the
  // real useCurrentUser reads it from cache without firing /api/users/me. klipy
  // key set so the hasKlipy assertion below exercises the truthy path.
  setCurrentUser({ id: "u1", display_name: "Alice", picture: null }, { klipy_api_key: "klipy-key" })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  // Drop the seeded viewer + cached document detail so tests stay isolated.
  queryClient.clear()
})

describe("DocumentEditor", () => {
  test("renders the editor for a collaborator, re-sourcing props from the detail query", async () => {
    routeShow(makeShow())

    await renderEditor()

    const body = await screen.findByTestId("editor-body")
    expect(body.getAttribute("data-document-id")).toBe("doc-1")
    expect(body.getAttribute("data-workspace-id")).toBe("ws-1")
    // upload_url + klipy flag come off the detail query / current user, not props.
    expect(body.getAttribute("data-upload-url")).toBe("/workspaces/ws-1/attachments")
    expect(body.getAttribute("data-has-klipy")).toBe("true")
    expect(body.getAttribute("data-current-user")).toBe("u1")

    const header = screen.getByTestId("editor-header")
    expect(header.getAttribute("data-title")).toBe("Quarterly Plan")
    expect(header.getAttribute("data-back-url")).toBe("/documents")
    expect(header.getAttribute("data-back-label")).toBe("Back to documents")
    // The subscription bell is built in-component from the workspace id.
    expect(header.getAttribute("data-bell-workspace")).toBe("ws-1")
    expect(header.getAttribute("data-bell-manage")).toBe("/notifications")
  })

  test("redirects a non-collaborator to the read-only show page, preserving return_to", async () => {
    routeShow(makeShow({ is_collaborator: false }))

    await renderEditor()

    const show = await screen.findByTestId("show-page")
    expect(show.getAttribute("data-return-to")).toBe("/documents")
    // The editor chrome never renders for a viewer who can't edit.
    expect(screen.queryByTestId("editor-body")).toBeNull()
  })

  test("offers a request-access affordance when the API denies access (403)", async () => {
    mockApiFetch.mockRejectedValue(new ApiError(403, { request_access_url: "/workspaces/ws-1/collaborators/access" }))

    await renderEditor()

    const link = await screen.findByTestId("request-document-access")
    expect(link.getAttribute("href")).toBe("/workspaces/ws-1/collaborators/access")
    expect(screen.queryByTestId("editor-body")).toBeNull()
  })
})
