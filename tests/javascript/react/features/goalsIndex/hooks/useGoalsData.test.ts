import { act, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import type { GoalListResponse } from "~/react/features/goalsIndex/types"
import type { Goal, GoalSummary } from "~/react/shared/types"
import { ChannelEventAction } from "~/types/channels"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
}))

vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: vi.fn(),
}))

vi.mock("~/shared/flash", () => ({
  showFlash: vi.fn(),
}))

// The reconnect catch-up subscribes to the channels client's "reconnected" event;
// hand the test a way to fire it.
let reconnectHandlers: (() => void)[] = []
vi.mock("~/channels/client", () => ({
  getChannelsClient: () => ({
    on: (event: string, handler: () => void) => {
      if (event === "reconnected") reconnectHandlers.push(handler)
    },
    off: (event: string, handler: () => void) => {
      reconnectHandlers = reconnectHandlers.filter(h => h !== handler)
    },
  }),
}))

// useGoalsData reads the current user's organization_id (the goals_index topic
// identity) via useCurrentUser; stub it so the subscription gate opens.
vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({
    user: { id: "u1", organization_id: "org-1" },
    clientConfig: null,
    loading: false,
    error: null,
  }),
}))

import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"

import { renderGoalsDataHook } from "../harness"

const mockApiFetch = vi.mocked(apiFetch)
const mockUseChannel = vi.mocked(useChannel)

function makeSubgoal(overrides: Partial<GoalSummary> = {}): GoalSummary {
  return {
    id: "subgoal-existing",
    workspace_id: "ws-1",
    title: "Existing subgoal",
    description: "",
    status: "active",
    progress: 0,
    target_date: null,
    is_completed: false,
    is_closed: false,
    is_draft: false,
    owner: null,
    group: null,
    open_comment_count: 0,
    ...overrides,
  }
}

function makeGoal(overrides: Partial<Goal> = {}): Goal {
  return {
    id: "goal-parent",
    workspace_id: "ws-1",
    title: "Parent goal",
    description: "",
    status: "active",
    progress: 0,
    target_date: null,
    start_date: null,
    is_completed: false,
    is_closed: false,
    is_draft: false,
    planning_list_name: null,
    created_at: "2026-06-17T00:00:00Z",
    owner: null,
    group: null,
    open_comment_count: 0,
    parent_id: null,
    parent: null,
    subgoals: [makeSubgoal()],
    ...overrides,
  }
}

function makeList(overrides: Partial<GoalListResponse> = {}): GoalListResponse {
  return { goals: [], planning_list_names: null, next_cursor: null, has_more: false, ...overrides }
}

function requestedUrls(): string[] {
  return mockApiFetch.mock.calls.map(([url]) => url as string)
}

// The GOALS_INDEX handler the hook registered — the broadcast's only entry point.
// useChannel signature: (target, resource, onMessage) — onMessage is arg 2.
function broadcast(payload: Record<string, unknown>) {
  const onBroadcast = mockUseChannel.mock.calls.at(-1)![2]
  act(() => onBroadcast(ChannelEventAction.UPDATED, payload))
}

afterEach(() => {
  reconnectHandlers = []
  vi.clearAllMocks()
})

describe("useGoalsData", () => {
  test("a GOALS_INDEX broadcast is the sole producer for a new subgoal (no optimistic append), so it appears exactly once and a single delete clears it", async () => {
    const parent = makeGoal()
    mockApiFetch.mockResolvedValue(makeList({ goals: [parent] }) as never)

    const { result } = await renderGoalsDataHook()

    await waitFor(() => expect(result.current.loading).toBe(false))

    // save_new_goal broadcasts the parent tree already containing the new subgoal.
    const parentWithNewSubgoal = makeGoal({
      subgoals: [makeSubgoal(), makeSubgoal({ id: "subgoal-new", title: "New subgoal" })],
    })
    broadcast({ goals: [parentWithNewSubgoal], has_more: false, next_cursor: null })

    // A cache write notifies observers on the next microtask, so the re-render is awaited.
    await waitFor(() =>
      expect(result.current.goals.find(g => g.id === parent.id)!.subgoals!.map(s => s.id)).toEqual([
        "subgoal-existing",
        "subgoal-new",
      ])
    )

    act(() => result.current.removeGoal("subgoal-new"))

    await waitFor(() =>
      expect(result.current.goals.find(g => g.id === parent.id)!.subgoals!.map(s => s.id)).toEqual([
        "subgoal-existing",
      ])
    )
  })

  test("subscribes to the goals_index topic by organization id and view", async () => {
    mockApiFetch.mockResolvedValue(makeList() as never)

    const { result } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.loading).toBe(false))

    const [target] = mockUseChannel.mock.calls.at(-1)!
    expect(target!.stream).toBe("goals_index")
    expect(target!.params).toEqual({ organization_id: "org-1", view: "active" })
  })

  test("fetches the active view on mount, requesting the subgoal tree", async () => {
    mockApiFetch.mockResolvedValue(makeList({ goals: [makeGoal()], has_more: true, next_cursor: "c1" }) as never)

    const { result } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.view).toBe("active")
    expect(result.current.hasMore).toBe(true)
    expect(requestedUrls()).toEqual([expect.stringContaining("expand=subgoals")])
    // The active view is the absence of a view param, not a positive one.
    expect(requestedUrls()[0]).not.toContain("is_closed")
    expect(requestedUrls()[0]).not.toContain("planning_list_name")
  })

  test.each([
    ["closed", "/goals?is_closed=true", "is_closed=true"],
    ["completed", "/goals?is_completed=true", "is_completed=true"],
  ])("derives the %s view from the URL and asks the API for it", async (view, url, expectedParam) => {
    mockApiFetch.mockResolvedValue(makeList() as never)

    const { result } = await renderGoalsDataHook([url])
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.view).toBe(view)
    expect(requestedUrls()[0]).toContain(expectedParam)
  })

  test("a planning list name in the URL becomes the view, even when it looks numeric", async () => {
    mockApiFetch.mockResolvedValue(makeList() as never)

    // The search parser coerces "2026" to a number; the validator must keep it a name.
    const { result } = await renderGoalsDataHook(["/goals?planning_list_name=2026"])
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.view).toBe("2026")
    expect(result.current.isPlanningList).toBe(true)
    expect(requestedUrls()[0]).toContain("planning_list_name=2026")
  })

  // Repeated keys are the legacy (server-generated and bookmarked) write form; a
  // JSON array is what navigate() now writes; a lone key is the single-value read
  // of the repeated form. All three must land as an array.
  test.each([
    ["repeated keys", "/goals?owner_ids=u1&owner_ids=u2", ["u1", "u2"]],
    ["a JSON array", `/goals?owner_ids=${encodeURIComponent('["u1","u2"]')}`, ["u1", "u2"]],
    ["a lone key", "/goals?owner_ids=u1", ["u1"]],
  ])("reads owner filters from %s in the URL", async (_form, url, expected) => {
    mockApiFetch.mockResolvedValue(makeList() as never)

    const { result } = await renderGoalsDataHook([url])
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.ownerIds).toEqual(expected)
    expect(result.current.isFiltered).toBe(true)
    for (const id of expected) expect(requestedUrls()[0]).toContain(`owner_ids=${id}`)
  })

  test("changeView navigates, clears the filters, and refetches", async () => {
    mockApiFetch.mockResolvedValue(makeList() as never)
    const { result, router } = await renderGoalsDataHook(["/goals?owner_ids=u1"])
    await waitFor(() => expect(result.current.loading).toBe(false))
    mockApiFetch.mockClear()

    act(() => result.current.changeView("closed"))

    await waitFor(() => expect(result.current.view).toBe("closed"))
    expect(router.state.location.search).toEqual({ is_closed: true })
    expect(result.current.ownerIds).toEqual([])
    await waitFor(() => expect(requestedUrls()[0]).toContain("is_closed=true"))
    expect(requestedUrls()[0]).not.toContain("owner_ids")
  })

  test("toggling an owner filter adds then removes it from the URL, preserving the view", async () => {
    mockApiFetch.mockResolvedValue(makeList() as never)
    const { result, router } = await renderGoalsDataHook(["/goals?is_closed=true"])
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.toggleOwnerFilter("u1"))
    await waitFor(() => expect(result.current.ownerIds).toEqual(["u1"]))
    expect(router.state.location.search).toMatchObject({ is_closed: true, owner_ids: ["u1"] })
    // navigate() writes an array as one JSON-encoded value rather than repeated
    // keys — accepted (a custom stringifySearch would be router-global), and safe
    // because reads tolerate both forms and nothing server-side emits these params.
    expect(decodeURIComponent(router.state.location.searchStr)).toContain('owner_ids=["u1"]')

    act(() => result.current.toggleOwnerFilter("u1"))
    await waitFor(() => expect(result.current.ownerIds).toEqual([]))
    // An empty filter normalizes out of the URL rather than serializing as [].
    expect(router.state.location.search).toEqual({ is_closed: true })
  })

  test("clearFilters drops both filters but keeps the view", async () => {
    mockApiFetch.mockResolvedValue(makeList() as never)
    const { result, router } = await renderGoalsDataHook(["/goals?planning_list_name=Q3&owner_ids=u1&group_ids=g1"])
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.clearFilters())

    await waitFor(() => expect(result.current.isFiltered).toBe(false))
    expect(router.state.location.search).toEqual({ planning_list_name: "Q3" })
    expect(result.current.view).toBe("Q3")
  })

  test("browser back restores the previous view", async () => {
    mockApiFetch.mockResolvedValue(makeList() as never)
    const { result, router } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.changeView("completed"))
    await waitFor(() => expect(result.current.view).toBe("completed"))

    await act(async () => router.history.back())

    await waitFor(() => expect(result.current.view).toBe("active"))
  })

  test("loadMore appends the next cursor page, deduped by id", async () => {
    mockApiFetch.mockImplementation((async (url: string) =>
      url.includes("cursor=")
        ? makeList({ goals: [makeGoal({ id: "b" }), makeGoal({ id: "c" })] })
        : makeList({
            goals: [makeGoal({ id: "a" }), makeGoal({ id: "b" })],
            has_more: true,
            next_cursor: "c1",
          })) as never)

    const { result } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.goals).toHaveLength(2))

    act(() => result.current.loadMore())

    await waitFor(() => expect(result.current.goals.map(g => g.id)).toEqual(["a", "b", "c"]))
  })

  test("sets error state on fetch failure", async () => {
    mockApiFetch.mockRejectedValue(new Error("boom"))
    const { result } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.error).toBe(true))
  })

  // --- Channel-first cache behaviour ---

  test("a broadcast replaces page 1 and leaves the pages a scrolled reader loaded intact", async () => {
    mockApiFetch.mockImplementation((async (url: string) =>
      url.includes("cursor=")
        ? makeList({ goals: [makeGoal({ id: "c" })] })
        : makeList({
            goals: [makeGoal({ id: "a" }), makeGoal({ id: "b" })],
            has_more: true,
            next_cursor: "c1",
          })) as never)

    const { result } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.goals).toHaveLength(2))
    act(() => result.current.loadMore())
    await waitFor(() => expect(result.current.goals.map(g => g.id)).toEqual(["a", "b", "c"]))
    mockApiFetch.mockClear()

    broadcast({
      goals: [makeGoal({ id: "a", description: "Edited" }), makeGoal({ id: "b" })],
      has_more: true,
      next_cursor: "c1",
    })

    await waitFor(() => expect(result.current.goals.find(g => g.id === "a")!.description).toBe("Edited"))
    expect(result.current.goals.map(g => g.id)).toEqual(["a", "b", "c"])
    // The payload is the page-1 listing, so patching it needs no network — and
    // nothing re-fetches page 2's goals just because they aren't in it.
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("a locally created goal survives the broadcast that omits it and is re-read for its generated title", async () => {
    mockApiFetch.mockResolvedValue(makeList({ goals: [makeGoal({ id: "a" })] }) as never)
    const { result } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.goals).toHaveLength(1))

    act(() => result.current.addGoalToList(makeGoal({ id: "new", title: null })))
    await waitFor(() => expect(result.current.goals.map(g => g.id)).toEqual(["a", "new"]))

    mockApiFetch.mockResolvedValue(makeGoal({ id: "new", title: "Generated" }) as never)
    broadcast({ goals: [makeGoal({ id: "a" })], has_more: false, next_cursor: null })

    await waitFor(() => expect(result.current.goals.map(g => g.id)).toEqual(["a", "new"]))
    expect(requestedUrls()).toContain("/api/goals/new?expand=subgoals")
    await waitFor(() => expect(result.current.goals.find(g => g.id === "new")!.title).toBe("Generated"))
  })

  test("a goal the broadcast already delivered is not appended again", async () => {
    mockApiFetch.mockResolvedValue(makeList({ goals: [makeGoal({ id: "a" })] }) as never)
    const { result } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.goals).toHaveLength(1))

    // The create POST resolves after its own broadcast already inserted the row.
    act(() => result.current.addGoalToList(makeGoal({ id: "a" })))

    await waitFor(() => expect(result.current.goals.map(g => g.id)).toEqual(["a"]))
  })

  test("a failed sort rolls the list back to the previous order", async () => {
    mockApiFetch.mockResolvedValue(makeList({ goals: [makeGoal({ id: "a" }), makeGoal({ id: "b" })] }) as never)
    const { result } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.goals.map(g => g.id)).toEqual(["a", "b"]))

    // Hold the sort POST open so the optimistic write is observable before the
    // rollback lands.
    let rejectSort: (error: Error) => void = () => {}
    mockApiFetch.mockImplementationOnce(
      (() =>
        new Promise((_resolve, reject) => {
          rejectSort = reject
        })) as never
    )
    act(() => result.current.reorderGoals([makeGoal({ id: "b" }), makeGoal({ id: "a" })]))
    await waitFor(() => expect(result.current.goals.map(g => g.id)).toEqual(["b", "a"]))

    await act(async () => rejectSort(new Error("boom")))

    await waitFor(() => expect(result.current.goals.map(g => g.id)).toEqual(["a", "b"]))
  })

  test("a socket reconnect merges page 1 rather than clobbering loaded pages", async () => {
    mockApiFetch.mockImplementation((async (url: string) =>
      url.includes("cursor=")
        ? makeList({ goals: [makeGoal({ id: "c" })] })
        : makeList({
            goals: [makeGoal({ id: "a" }), makeGoal({ id: "b" })],
            has_more: true,
            next_cursor: "c1",
          })) as never)

    const { result } = await renderGoalsDataHook()
    await waitFor(() => expect(result.current.goals).toHaveLength(2))
    act(() => result.current.loadMore())
    await waitFor(() => expect(result.current.goals.map(g => g.id)).toEqual(["a", "b", "c"]))

    mockApiFetch.mockResolvedValue(
      makeList({ goals: [makeGoal({ id: "a", description: "Missed" })], has_more: true, next_cursor: "c1" }) as never
    )
    await act(async () => {
      reconnectHandlers.forEach(handler => handler())
    })

    await waitFor(() => expect(result.current.goals.find(g => g.id === "a")!.description).toBe("Missed"))
    expect(result.current.goals.map(g => g.id)).toEqual(["a", "c"])
  })
})
