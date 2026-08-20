import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { SearchResponse } from "../../../../../app/javascript/react/shared/searchResults"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
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
import { SearchResults } from "../../../../../app/javascript/react/features/searchResults/SearchResults"

const mockApiFetch = vi.mocked(apiFetch)

const searchResponse: SearchResponse = {
  results: [
    {
      id: "1",
      title: "Q2 Planning",
      author: "Alice",
      content_type: "document",
      category: "document",
      source_url: "/docs/1",
      preview_content: "Our quarterly plan",
      created_at: "2026-04-14T00:00:00Z",
      updated_at: "2026-04-14T00:00:00Z",
      relevance_score: null,
      metadata: {},
      shared_with_me: false,
    },
    {
      id: "2",
      title: "Sprint Review",
      author: "Bob",
      content_type: "meeting",
      category: "activity",
      source_url: "/meetings/2",
      preview_content: null,
      created_at: "2026-04-13T00:00:00Z",
      updated_at: "2026-04-13T00:00:00Z",
      relevance_score: null,
      metadata: {},
      shared_with_me: false,
    },
  ],
  query: "planning",
  content_type: null,
  hero_count: 0,
}

beforeEach(() => {
  mockApiFetch.mockReset()

  Object.defineProperty(window, "location", {
    value: { search: "", href: "" },
    writable: true,
    configurable: true,
  })
  window.history.replaceState = vi.fn()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("SearchResults", () => {
  test("renders loading spinner during fetch", () => {
    mockApiFetch.mockReturnValue(new Promise(() => {}))

    const { container } = render(<SearchResults initialQuery="test query" />)

    expect(container.querySelector(".loading-spinner")).toBeTruthy()
  })

  test("renders empty prompt when no query", () => {
    render(<SearchResults initialQuery="" />)

    expect(screen.getByText("Enter a search query to find content")).toBeTruthy()
  })

  test("renders results in tabular layout", async () => {
    mockApiFetch.mockResolvedValue(searchResponse as any)

    render(<SearchResults initialQuery="planning" />)

    await waitFor(() => {
      expect(screen.getByText((_, el) => el?.tagName === "P" && el?.textContent === "Q2 Planning")).toBeTruthy()
    })

    expect(screen.getByText((_, el) => el?.tagName === "P" && el?.textContent === "Sprint Review")).toBeTruthy()
    expect(screen.getByText("Alice")).toBeTruthy()
    expect(screen.getByText("Bob")).toBeTruthy()
    expect(
      screen.getByText((_, el) => el?.tagName === "P" && el?.textContent === "Our quarterly plan")
    ).toBeTruthy()
  })

  test("highlights matching query terms in results", async () => {
    mockApiFetch.mockResolvedValue(searchResponse as any)

    const { container } = render(<SearchResults initialQuery="planning" />)

    await waitFor(() => {
      expect(screen.getByText((_, el) => el?.tagName === "P" && el?.textContent === "Q2 Planning")).toBeTruthy()
    })

    const marks = container.querySelectorAll("mark")
    expect(marks.length).toBeGreaterThanOrEqual(1)

    const markTexts = Array.from(marks).map(m => m.textContent?.toLowerCase())
    expect(markTexts.some(t => t === "planning" || t === "plan")).toBe(true)
  })

  test("renders no results message", async () => {
    mockApiFetch.mockResolvedValue({ results: [], query: "xyzzy", content_type: null, hero_count: 0 } as any)

    render(<SearchResults initialQuery="xyzzy" />)

    await waitFor(() => {
      expect(screen.getByText(/No results found/)).toBeTruthy()
    })
  })

  test("filter chips trigger re-fetch with content_type", async () => {
    mockApiFetch.mockResolvedValue(searchResponse as any)

    render(<SearchResults initialQuery="planning" />)

    await waitFor(() => {
      expect(screen.getByText((_, el) => el?.tagName === "P" && el?.textContent === "Q2 Planning")).toBeTruthy()
    })

    mockApiFetch.mockClear()
    mockApiFetch.mockResolvedValue({ results: [], query: "planning", content_type: "meeting", hero_count: 0 } as any)

    // Open the filter dropdown, then select "Meetings"
    fireEvent.click(screen.getByText("Everything"))
    fireEvent.click(screen.getByText("Meetings"))

    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining("content_type=meeting"),
      expect.any(Object)
    )
  })

  test("renders error state on fetch failure", async () => {
    mockApiFetch.mockRejectedValue(new Error("fail"))

    render(<SearchResults initialQuery="test query" />)

    await waitFor(() => {
      expect(screen.getByText("Something went wrong")).toBeTruthy()
    })
  })
})
