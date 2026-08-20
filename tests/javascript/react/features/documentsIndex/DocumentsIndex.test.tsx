import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  errorMessage: (_error: unknown, fallback: string) => fallback,
  ApiError: class extends Error {
    status: number
    body: null
    constructor(status: number) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = null
    }
  },
}))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { DocumentsIndex } from "../../../../../app/javascript/react/features/documentsIndex/DocumentsIndex"
import type {
  DocumentListItem,
  DocumentListResponse,
} from "../../../../../app/javascript/react/features/documentsIndex/types"
import type { SearchResponse } from "../../../../../app/javascript/react/shared/searchResults"
import { renderInDocumentsRouter } from "./harness"

const mockApiFetch = vi.mocked(apiFetch)

function makeDocument(overrides: Partial<DocumentListItem> = {}): DocumentListItem {
  return {
    id: "doc-1",
    title: "Project Plan",
    author_display_name: "Alice",
    last_viewed_at: "2026-04-20T09:00:00Z",
    updated_at: "2026-04-20T09:00:00Z",
    comment_count: 0,
    sharing: "private",
    collaborator_count: 1,
    source_url: "/documents/doc-1",
    ...overrides,
  }
}

function makeListResponse(overrides: Partial<DocumentListResponse> = {}): DocumentListResponse {
  return { documents: [makeDocument()], next_cursor: null, has_more: false, ...overrides }
}

// Routes apiFetch by URL/method so browse, search, and create can all be in flight.
function routeApiFetch({
  list = makeListResponse({ documents: [] }),
  search,
  created,
}: {
  list?: DocumentListResponse
  search?: SearchResponse
  created?: { id: string }
} = {}) {
  mockApiFetch.mockImplementation(async (url: string, options?: RequestInit) => {
    if (url.startsWith("/api/documents") && options?.method === "POST") return created ?? { id: "new-doc" }
    if (url.startsWith("/api/documents")) return list
    if (url.startsWith("/api/search")) return search ?? { results: [], query: "", content_type: "document" }
    throw new Error(`unexpected fetch: ${url}`)
  })
}

const assignSpy = vi.fn()

beforeEach(() => {
  mockApiFetch.mockReset()
  assignSpy.mockReset()
  // createMemoryHistory drives router navigation, so window.location is only
  // touched by the search-result full-page load (gid links); stub it.
  Object.defineProperty(window, "location", {
    value: { ...window.location, assign: assignSpy },
    writable: true,
    configurable: true,
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("DocumentsIndex", () => {
  test("renders rows and links each to the show route carrying return_to", async () => {
    routeApiFetch({ list: makeListResponse({ documents: [makeDocument({ id: "d1", title: "Q2 Plan" })] }) })

    await renderInDocumentsRouter(DocumentsIndex)

    const link = await screen.findByRole("link", { name: /Q2 Plan/ })
    const href = link.getAttribute("href") ?? ""
    expect(href).toContain("/documents/d1")
    expect(href).toContain("return_to")
    expect(mockApiFetch).toHaveBeenCalledWith("/api/documents", expect.any(Object))
  })

  test("changing the filter navigates the index URL and refetches", async () => {
    routeApiFetch()

    const { router } = await renderInDocumentsRouter(DocumentsIndex)
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/documents", expect.any(Object)))

    fireEvent.click(screen.getByRole("button", { name: "Owned by me" }))
    fireEvent.click(screen.getByRole("button", { name: "Owned by anyone" }))

    await waitFor(() => expect(router.state.location.search).toMatchObject({ filter: "anyone" }))
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/documents?filter=anyone", expect.any(Object)))
  })

  test("renders empty state when there are no documents", async () => {
    routeApiFetch({ list: makeListResponse({ documents: [] }) })

    await renderInDocumentsRouter(DocumentsIndex)

    expect(await screen.findByText("No documents yet")).toBeTruthy()
  })

  test("typing flips to search mode, searches, and syncs q to the URL", async () => {
    const search: SearchResponse = {
      results: [
        {
          id: "search-1",
          title: "Search Hit",
          author: "Bob",
          content_type: "document",
          category: "document",
          // /api/search returns server-resolved gid links for documents, not
          // /documents/{id} — the result link must point at this URL verbatim
          // (full-load, gid_redirect resolves it), never a client-parsed id.
          source_url: "/gid/Z2lkOi8vZGVjaWRlL0RvY3VtZW50L2FiYw",
          preview_content: null,
          created_at: "2026-04-21T09:00:00Z",
          updated_at: "2026-04-21T09:00:00Z",
          relevance_score: null,
          metadata: {},
          shared_with_me: false,
        },
      ],
      query: "hit",
      content_type: "document",
    }
    routeApiFetch({ list: makeListResponse({ documents: [makeDocument({ title: "Browse Doc" })] }), search })

    const { router } = await renderInDocumentsRouter(DocumentsIndex)
    await screen.findByText("Browse Doc")

    fireEvent.click(screen.getByLabelText("Search documents"))
    fireEvent.change(screen.getByPlaceholderText("Search documents..."), { target: { value: "hit" } })

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("content_type=document"), expect.any(Object))
    )
    // highlightMatches splits the title across <mark> nodes, so match on the link's text.
    const resultLink = await waitFor(() => {
      const link = screen.getAllByRole("link").find(a => a.textContent?.includes("Search Hit"))
      expect(link).toBeTruthy()
      return link!
    })
    // The href targets the gid URL the server gave us (with return_to), not a
    // mangled /documents/<gid-param>.
    expect(resultLink.getAttribute("href")).toContain("/gid/Z2lkOi8vZGVjaWRlL0RvY3VtZW50L2FiYw")
    await waitFor(() => expect(router.state.location.search).toMatchObject({ q: "hit" }))
    expect(screen.queryByText("Browse Doc")).toBeNull()
  })

  test("a deep link with q opens directly in search mode", async () => {
    const search: SearchResponse = {
      results: [
        {
          id: "s",
          title: "Direct Hit",
          author: null,
          content_type: "document",
          category: "document",
          source_url: "/documents/s",
          preview_content: null,
          created_at: "2026-04-21T09:00:00Z",
          updated_at: "2026-04-21T09:00:00Z",
          relevance_score: null,
          metadata: {},
          shared_with_me: false,
        },
      ],
      query: "hit",
      content_type: "document",
    }
    routeApiFetch({ list: makeListResponse({ documents: [] }), search })

    await renderInDocumentsRouter(DocumentsIndex, ["/documents?q=hit"])

    await waitFor(() =>
      expect(screen.getAllByRole("link").some(a => a.textContent?.includes("Direct Hit"))).toBe(true)
    )
    expect(screen.queryByRole("button", { name: /New document/ })).toBeNull()
  })

  test("New document POSTs and client-navigates to the editor", async () => {
    routeApiFetch({ list: makeListResponse({ documents: [] }), created: { id: "fresh-doc" } })

    await renderInDocumentsRouter(DocumentsIndex)
    await screen.findByText("No documents yet")

    fireEvent.click(screen.getByRole("button", { name: "New document" }))

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith("/api/documents", expect.objectContaining({ method: "POST" }))
    )
    // Client navigation to the editor route (not a full-page load).
    const edit = await screen.findByTestId("edit-page")
    expect(edit.getAttribute("data-document-id")).toBe("fresh-doc")
    expect(assignSpy).not.toHaveBeenCalled()
  })
})
