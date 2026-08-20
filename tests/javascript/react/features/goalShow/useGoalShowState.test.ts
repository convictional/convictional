import { act } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
}))

import { useGoalShowState } from "~/react/features/goalShow/hooks/useGoalShowState"
import { apiFetch } from "~/react/shared/apiFetch"

import { renderHookWithClient, waitFor } from "../../shared/testUtils"

const mockApiFetch = vi.mocked(apiFetch)

function makeGoal(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    workspace_id: "ws-1",
    title: null,
    description: "Test goal",
    status: "on_track",
    progress: 0.5,
    target_date: null,
    start_date: null,
    icon_name: null,
    icon_color: null,
    is_completed: false,
    is_closed: false,
    is_draft: false,
    planning_list_name: null,
    created_at: "2026-01-01T00:00:00Z",
    owner: { id: "user-1", display_name: "Alice", picture: null },
    group: null,
    open_comment_count: 0,
    subgoals: [],
    ...overrides,
  }
}

function goalIdFromUrl(url: string): string {
  const match = url.match(/\/api\/goals\/([^/?]+)/)
  return match ? match[1] : ""
}

mockApiFetch.mockImplementation((url: string) => Promise.resolve(makeGoal(goalIdFromUrl(url)) as never))

describe("useGoalShowState", () => {
  test("loads the goal and applies updates to it", async () => {
    const { result } = renderHookWithClient(() => useGoalShowState("A"))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.goal?.id).toBe("A")

    act(() => {
      result.current.handleGoalUpdated(makeGoal("A", { description: "Changed" }) as never)
    })
    // A cache write notifies observers on the next microtask, so the re-render is awaited.
    await waitFor(() => expect(result.current.goal?.description).toBe("Changed"))
    expect(result.current.goal?.id).toBe("A")
  })

  test("forwards mailbox_entry_id and splits the entry off the goal entity", async () => {
    mockApiFetch.mockImplementationOnce(
      (() => Promise.resolve({ ...makeGoal("A"), mailbox_entry: { id: "e1", is_unread: true } })) as never
    )

    const { result } = renderHookWithClient(() => useGoalShowState("A", "e1"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("mailbox_entry_id=e1"), expect.anything())
    expect(result.current.mailboxEntry?.id).toBe("e1")
    expect(result.current.goal).not.toHaveProperty("mailbox_entry")
  })

  test("a mailbox action bar write leaves the goal alone, and a goal PATCH leaves the entry alone", async () => {
    mockApiFetch.mockImplementationOnce(
      (() => Promise.resolve({ ...makeGoal("A"), mailbox_entry: { id: "e1", is_unread: true } })) as never
    )

    const { result } = renderHookWithClient(() => useGoalShowState("A", "e1"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.setMailboxEntry({ id: "e1", is_unread: false } as never))
    await waitFor(() => expect(result.current.mailboxEntry?.is_unread).toBe(false))
    expect(result.current.goal?.id).toBe("A")

    act(() => result.current.handleGoalUpdated(makeGoal("A", { description: "Changed" }) as never))
    await waitFor(() => expect(result.current.goal?.description).toBe("Changed"))
    expect(result.current.mailboxEntry?.id).toBe("e1")
  })

  test("refetchGoal re-reads the goal with the show page's expansions", async () => {
    const { result } = renderHookWithClient(() => useGoalShowState("A"))
    await waitFor(() => expect(result.current.loading).toBe(false))
    mockApiFetch.mockClear()

    act(() => result.current.refetchGoal())

    // Reactivate's own response omits parent/subgoals (the menu POSTs no expand),
    // so the refetch must carry them.
    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/A?expand=subgoals&expand=parent", expect.anything())
    )
    expect(result.current.goal?.id).toBe("A")
  })
})
