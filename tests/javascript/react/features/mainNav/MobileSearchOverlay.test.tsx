import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {},
  errorMessage: () => "error",
}))

vi.mock("~/react/ui/DateTime", () => ({
  DateTime: ({ datetime }: { datetime: string }) => <span>{datetime}</span>,
}))

import { apiFetch } from "~/react/shared/apiFetch"
import type { LookupResult } from "~/react/shared/lookup"
import { MobileSearchOverlay } from "../../../../../app/javascript/react/features/mainNav/MobileSearchOverlay"

const mockApiFetch = vi.mocked(apiFetch)

function makeResult(overrides: Partial<LookupResult> = {}): LookupResult {
  return {
    id: "id-1",
    content_type: "document",
    title: "Result title",
    url: "/documents/id-1",
    updated_at: "2026-01-01T00:00:00Z",
    display_at: "2026-01-01T00:00:00Z",
    authors: [],
    preview: null,
    shared_with_me: false,
    email: null,
    avatar_url: null,
    global_id: "gid://convictional/Document/id-1",
    ...overrides,
  }
}

function makePerson(overrides: Partial<LookupResult> = {}): LookupResult {
  return makeResult({
    content_type: "user",
    title: "Adam McCabe",
    email: "adam@example.com",
    global_id: "gid://convictional/User/u-1",
    ...overrides,
  })
}

// Routes mock apiFetch responses by URL so a single test can return both lookup
// results and track POSTs without juggling mockResolvedValueOnce ordering.
function routeApi(routes: Record<string, unknown>) {
  mockApiFetch.mockImplementation(async (url: string) => {
    for (const prefix in routes) {
      if (url.startsWith(prefix)) return routes[prefix]
    }
    return null
  })
}

describe("MobileSearchOverlay", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.stubGlobal("scrollTo", vi.fn())
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  function open() {
    act(() => {
      window.dispatchEvent(new CustomEvent("mobile-search:open"))
    })
  }

  test("does not render until mobile-search:open is dispatched", () => {
    render(<MobileSearchOverlay />)
    expect(screen.queryByRole("button", { name: "Close search" })).toBeNull()
  })

  test("opens on mobile-search:open event and shows search UI", () => {
    render(<MobileSearchOverlay />)
    open()

    expect(screen.getByRole("button", { name: "Close search" })).toBeInTheDocument()
    expect(screen.getByText("Search across all your content")).toBeInTheDocument()
  })

  test("fetches results after debounce when typing", async () => {
    mockApiFetch.mockResolvedValue({ results: { user_results: [], other_results: [] }, query: "" })

    render(<MobileSearchOverlay />)
    open()

    // Advance past rAF for morph animation
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const input = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input, { target: { value: "test query" } })

    // Advance past debounce
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/commands/lookup?query=test+query"),
      expect.any(Object)
    )
  })

  test("does not fetch for queries shorter than 2 characters", async () => {
    render(<MobileSearchOverlay />)
    open()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const input = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input, { target: { value: "t" } })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("closes on Escape key", async () => {
    render(<MobileSearchOverlay />)
    open()

    expect(screen.getByRole("button", { name: "Close search" })).toBeInTheDocument()

    fireEvent.keyDown(screen.getByRole("button", { name: "Close search" }).closest("div[class*='fixed']")!, {
      key: "Escape",
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350)
    })

    expect(screen.queryByRole("button", { name: "Close search" })).toBeNull()
  })

  test("closes on close button click", async () => {
    render(<MobileSearchOverlay />)
    open()

    fireEvent.click(screen.getByRole("button", { name: "Close search" }))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350)
    })

    expect(screen.queryByRole("button", { name: "Close search" })).toBeNull()
  })

  test("tapping a person switches to the people endpoint and renders the filter chip", async () => {
    const person = makePerson()
    routeApi({
      "/api/commands/lookup": { results: { user_results: [person], other_results: [] }, query: "" },
      "/api/commands/people": {
        results: { user_results: [], other_results: [makeResult({ id: "doc-1", title: "Adam's doc" })] },
        query: "",
        filter: null,
      },
    })

    render(<MobileSearchOverlay />)
    open()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const input = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input, { target: { value: "adam" } })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    fireEvent.click(document.querySelector('button[data-position="0"]')!)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })

    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/commands/people?author_gid=${encodeURIComponent(person.global_id)}`),
      expect.any(Object)
    )
    expect(screen.getByRole("button", { name: "Clear filter" })).toBeInTheDocument()
  })

  test("clearing the filter chip restores the lookup endpoint", async () => {
    const person = makePerson()
    routeApi({
      "/api/commands/lookup": { results: { user_results: [person], other_results: [] }, query: "" },
      "/api/commands/people": { results: { user_results: [], other_results: [] }, query: "", filter: null },
    })

    render(<MobileSearchOverlay />)
    open()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const input = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input, { target: { value: "adam" } })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    fireEvent.click(document.querySelector('button[data-position="0"]')!)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })

    // Type a query while filtered so we can observe which endpoint runs after clear
    const input2 = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input2, { target: { value: "notes" } })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    mockApiFetch.mockClear()
    fireEvent.click(screen.getByRole("button", { name: "Clear filter" }))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })

    expect(screen.queryByRole("button", { name: "Clear filter" })).toBeNull()
    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("/api/commands/lookup?"), expect.any(Object))
    expect(mockApiFetch).not.toHaveBeenCalledWith(expect.stringContaining("/api/commands/people"), expect.any(Object))
  })

  test("'See all results' link appears at the threshold and links to /search", async () => {
    const tenResults = Array.from({ length: 10 }, (_, i) => makeResult({ id: `doc-${i}`, title: `Doc ${i}` }))
    routeApi({
      "/api/commands/lookup": { results: { user_results: [], other_results: tenResults }, query: "" },
    })

    render(<MobileSearchOverlay />)
    open()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const input = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input, { target: { value: "doc" } })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    const seeAll = screen.getByText(/See all results/i).closest("a")
    expect(seeAll).not.toBeNull()
    expect(seeAll!.getAttribute("href")).toBe(`/search?q=${encodeURIComponent("doc")}`)
  })

  test("'See all results' link is hidden below the threshold", async () => {
    const nineResults = Array.from({ length: 9 }, (_, i) => makeResult({ id: `doc-${i}` }))
    routeApi({
      "/api/commands/lookup": { results: { user_results: [], other_results: nineResults }, query: "" },
    })

    render(<MobileSearchOverlay />)
    open()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const input = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input, { target: { value: "doc" } })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    expect(screen.queryByText(/See all results/i)).toBeNull()
  })

  test("trackSearch sends the session payload on close (no clicked fields)", async () => {
    const r1 = makeResult({ id: "doc-1" })
    const r2 = makeResult({ id: "doc-2" })
    routeApi({
      "/api/commands/lookup": { results: { user_results: [], other_results: [r1, r2] }, query: "" },
      "/api/commands/lookup/track": null,
    })

    render(<MobileSearchOverlay />)
    open()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const input = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input, { target: { value: "test query" } })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    fireEvent.click(screen.getByRole("button", { name: "Close search" }))

    const trackCall = mockApiFetch.mock.calls.find(([url]) => String(url) === "/api/commands/lookup/track")
    expect(trackCall).toBeDefined()
    const body = JSON.parse((trackCall![1] as { body: string }).body)
    expect(body).toMatchObject({
      query: "test query",
      result_count: 2,
      result_ids: ["doc-1", "doc-2"],
    })
    expect(body.clicked_content_id).toBeUndefined()
    expect(body.clicked_position).toBeUndefined()
  })

  test("trackSearch sends clicked_content_id and clicked_position when a result is tapped", async () => {
    const r1 = makeResult({ id: "doc-1" })
    const r2 = makeResult({ id: "doc-2", title: "Second doc" })
    routeApi({
      "/api/commands/lookup": { results: { user_results: [], other_results: [r1, r2] }, query: "" },
      "/api/commands/lookup/track": null,
    })

    render(<MobileSearchOverlay />)
    open()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const input = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input, { target: { value: "test query" } })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    fireEvent.click(screen.getByText("Second doc").closest("a")!)

    const trackCall = mockApiFetch.mock.calls.find(([url]) => String(url) === "/api/commands/lookup/track")
    expect(trackCall).toBeDefined()
    const body = JSON.parse((trackCall![1] as { body: string }).body)
    expect(body).toMatchObject({
      query: "test query",
      result_count: 2,
      result_ids: ["doc-1", "doc-2"],
      clicked_content_id: "doc-2",
      clicked_position: 1,
    })
  })

  test("track payload does not leak across overlay sessions when a fetch resolves during close", async () => {
    let resolveSecond: ((value: unknown) => void) | undefined
    mockApiFetch.mockImplementation(async (url: string) => {
      if (url.startsWith("/api/commands/lookup/track")) return null
      if (url.includes("query=first")) {
        return { results: { user_results: [], other_results: [makeResult({ id: "first-1" })] }, query: "first" }
      }
      if (url.includes("query=second")) {
        // Resolves only when we trigger it — simulates a fetch landing during the close animation
        return new Promise(resolve => {
          resolveSecond = resolve
        })
      }
      return null
    })

    render(<MobileSearchOverlay />)
    open()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const input = document.querySelector("input[type='text']") as HTMLInputElement

    // Session 1: type "first", let results land, then close
    fireEvent.change(input, { target: { value: "first" } })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    // Start an in-flight request that hasn't resolved yet
    fireEvent.change(input, { target: { value: "second" } })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })

    // Close — the pending /second/ promise resolves mid-animation, before the abort fires
    fireEvent.click(screen.getByRole("button", { name: "Close search" }))
    await act(async () => {
      resolveSecond?.({ results: { user_results: [], other_results: [makeResult({ id: "stale-1" })] }, query: "second" })
      await vi.advanceTimersByTimeAsync(400) // past the 300ms close timeout
    })

    mockApiFetch.mockClear()
    mockApiFetch.mockImplementation(async (url: string) => {
      if (url.startsWith("/api/commands/lookup/track")) return null
      return { results: { user_results: [], other_results: [makeResult({ id: "new-1" })] }, query: "new" }
    })

    // Session 2: open again, type, close — the leaked "stale-1" must not appear in track
    open()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    const input2 = document.querySelector("input[type='text']") as HTMLInputElement
    fireEvent.change(input2, { target: { value: "new" } })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    fireEvent.click(screen.getByRole("button", { name: "Close search" }))

    const trackCalls = mockApiFetch.mock.calls.filter(([url]) => String(url) === "/api/commands/lookup/track")
    expect(trackCalls.length).toBe(1)
    const body = JSON.parse((trackCalls[0]![1] as { body: string }).body)
    expect(body.query).toBe("new")
    expect(body.result_ids).toEqual(["new-1"])
  })
})
