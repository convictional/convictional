import { act, fireEvent, render, waitFor } from "../../shared/testUtils"
import { beforeEach, describe, expect, test, vi } from "vitest"

import type { LookupResult } from "../../../../../app/javascript/react/shared/lookup"
import type { RecentItem } from "../../../../../app/javascript/react/features/commandPalette/types"

// commandPalette/api.ts re-exports fetchLookup/fetchPeople/trackSearch from
// ~/react/shared/lookup, and CommandPalette imports them from ./api, so mocking
// the source module intercepts them. Hoisted so the factory can share the same
// content row the assertions seed into the store.
const { contentResult } = vi.hoisted(() => ({
  contentResult: {
    id: "content-1",
    content_type: "email_thread",
    title: "Q3 planning",
    url: "/email_threads/abc",
    authors: ["Alice"],
    preview: null,
    shared_with_me: false,
    email: null,
    avatar_url: null,
    global_id: "gid://email_thread/abc",
    updated_at: "2026-07-01T00:00:00Z",
    display_at: "2026-07-01T00:00:00Z",
  } satisfies LookupResult,
}))

vi.mock("../../../../../app/javascript/react/shared/lookup", () => ({
  trackSearch: vi.fn(),
  fetchLookup: vi.fn().mockResolvedValue({ results: { user_results: [], other_results: [] }, query: "" }),
  fetchPeople: vi
    .fn()
    .mockResolvedValue({ results: { user_results: [], other_results: [contentResult] }, query: "", filter: null }),
}))

import { CommandPalette } from "../../../../../app/javascript/react/features/commandPalette/CommandPalette"
import { usePaletteStore } from "../../../../../app/javascript/react/features/commandPalette/store"
import { trackSearch } from "../../../../../app/javascript/react/shared/lookup"

const mockTrackSearch = vi.mocked(trackSearch)

const personResult: LookupResult = {
  id: "person-1",
  content_type: "user",
  title: "Alice",
  url: "/users/xyz",
  authors: [],
  preview: null,
  shared_with_me: false,
  email: "alice@example.com",
  avatar_url: null,
  global_id: "gid://user/xyz",
  updated_at: "2026-07-01T00:00:00Z",
  display_at: "2026-07-01T00:00:00Z",
}

const recentItem: RecentItem = {
  workspace_id: "ws-1",
  resource_type: "EmailThread",
  title: "Post-demo follow-up",
  url: "/email_threads/recent-1",
  updated_at: "2026-07-01T00:00:00Z",
  collaborators: [{ id: "user-1", display_name: "Alice" }],
  preview: null,
}

function paletteRow(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[data-test-id="palette-result"]')
}

// Recent rows render through ResultRow without a testId, so select them by href.
function recentRow(): HTMLElement | null {
  return document.querySelector<HTMLElement>(`a[href="${recentItem.url}"]`)
}

beforeEach(() => {
  mockTrackSearch.mockClear()
  act(() =>
    usePaletteStore.setState({
      isOpen: false,
      filterGlobalId: null,
      results: null,
      pendingTracking: null,
      mode: "recent",
      input: "",
      query: "",
    })
  )
})

describe("CommandPalette result activation", () => {
  test("content result activation closes the palette while still flushing tracking", async () => {
    render(<CommandPalette />)

    act(() =>
      usePaletteStore.setState({
        isOpen: true,
        mode: "search",
        query: "planning",
        input: "",
        filterGlobalId: null,
        results: { user_results: [], other_results: [contentResult] },
        pendingTracking: { query: "planning", resultIds: ["content-1"], resultCount: 1, filterGid: null },
      })
    )

    const row = paletteRow()
    expect(row).not.toBeNull()
    fireEvent.click(row!)

    expect(usePaletteStore.getState().isOpen).toBe(false)
    expect(mockTrackSearch).toHaveBeenCalledTimes(1)
    expect(mockTrackSearch).toHaveBeenCalledWith(
      expect.objectContaining({ clicked_content_id: "content-1", clicked_position: 0 })
    )

    // Drilled-into-contact flow: filterGlobalId is set. A content result activated
    // while a contact filter is active must still close the palette (the reported bug).
    act(() =>
      usePaletteStore.setState({
        isOpen: true,
        mode: "search",
        query: "planning",
        input: "",
        filterGlobalId: "gid://contact/qrs",
        results: { user_results: [], other_results: [contentResult] },
        pendingTracking: { query: "planning", resultIds: ["content-1"], resultCount: 1, filterGid: null },
      })
    )

    await waitFor(() => expect(paletteRow()).not.toBeNull())
    fireEvent.click(paletteRow()!)

    expect(usePaletteStore.getState().isOpen).toBe(false)
  })

  test("recent item activation closes the palette", () => {
    render(<CommandPalette />)

    // Recent is the palette's default view (no query); its boosted-anchor rows must close it too.
    act(() =>
      usePaletteStore.setState({
        isOpen: true,
        mode: "recent",
        query: "",
        input: "",
        filterGlobalId: null,
        recent: [recentItem],
      })
    )

    const row = recentRow()
    expect(row).not.toBeNull()
    fireEvent.click(row!)

    expect(usePaletteStore.getState().isOpen).toBe(false)
    // Recent items are not search results, so no tracking is flushed.
    expect(mockTrackSearch).not.toHaveBeenCalled()
  })

  test("person result activation keeps the palette open and sets an author filter", () => {
    render(<CommandPalette />)

    act(() =>
      usePaletteStore.setState({
        isOpen: true,
        mode: "search",
        query: "alice",
        input: "",
        filterGlobalId: null,
        results: { user_results: [personResult], other_results: [] },
      })
    )

    const row = paletteRow()
    expect(row).not.toBeNull()
    fireEvent.click(row!)

    expect(usePaletteStore.getState().isOpen).toBe(true)
    expect(usePaletteStore.getState().filterGlobalId).toBe(personResult.global_id)
  })
})
