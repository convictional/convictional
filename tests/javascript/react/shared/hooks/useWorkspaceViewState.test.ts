import { renderHook } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"

import type { CollaboratorViewState, WorkspaceCollaboratorsData } from "~/react/shared/types"

// Stub the shared collaborators query; useWorkspaceViewState is pure derivation over its data.
let queryData: WorkspaceCollaboratorsData | undefined
vi.mock("~/react/shared/hooks/useWorkspaceCollaboratorsQuery", () => ({
  useWorkspaceCollaboratorsQuery: () => ({ data: queryData }),
}))

import { useWorkspaceViewState } from "~/react/shared/hooks/useWorkspaceViewState"

function viewState(lastViewedEventId: string | null): CollaboratorViewState {
  return { viewed: !!lastViewedEventId, last_viewed_at: null, last_viewed_event_id: lastViewedEventId }
}

function collaborator(userId: string, lastViewedEventId: string | null) {
  return {
    id: `collab-${userId}`,
    user: { id: userId, display_name: userId, picture: null },
    is_removable: true,
    status: "approved" as const,
    view_state: viewState(lastViewedEventId),
  }
}

function data(overrides: Partial<WorkspaceCollaboratorsData> = {}): WorkspaceCollaboratorsData {
  return {
    collaborators: [],
    pending: [],
    viewers: [],
    present_user_ids: [],
    current_user_view_state: viewState(null),
    ...overrides,
  }
}

describe("useWorkspaceViewState", () => {
  test("derives readers from collaborators and non-collaborator viewers, excluding the current user", () => {
    queryData = data({
      collaborators: [
        collaborator("me", "e2"),
        collaborator("alice", "e1"),
        collaborator("bob", "e1"),
        collaborator("carol", null), // never viewed → not a reader anywhere
      ],
      // A non-collaborator viewer (org member on a shared goal) — regression guard: must appear.
      viewers: [{ user: { id: "orgmember", display_name: "Org Member", picture: null }, view_state: viewState("e1") }],
      current_user_view_state: viewState("e2"),
    })

    const { result } = renderHook(() => useWorkspaceViewState("ws-1", "me"))

    expect(result.current.readersByEventId.get("e1")?.map(u => u.id).sort()).toEqual(["alice", "bob", "orgmember"])
    expect(result.current.readersByEventId.has("e2")).toBe(false) // current user is never their own reader
    expect(result.current.ready).toBe(true)
  })

  test("anchors lastSeenEventId on the current user's arrival cursor", () => {
    queryData = data({ collaborators: [collaborator("alice", "e1")], current_user_view_state: viewState("e1") })
    const { result } = renderHook(() => useWorkspaceViewState("ws-1", "me"))
    expect(result.current.lastSeenEventId).toBe("e1")
  })

  test("freezes lastSeenEventId at arrival even after the cursor advances on refetch", () => {
    // The user's own visit records as the page loads, and later refetches (e.g. from another viewer's
    // activity) return an advanced cursor — the divider must stay anchored where the user arrived.
    queryData = data({ current_user_view_state: viewState("e1") })
    const { result, rerender } = renderHook(() => useWorkspaceViewState("ws-1", "me"))
    expect(result.current.lastSeenEventId).toBe("e1")

    queryData = data({ current_user_view_state: viewState("e5") }) // cursor advanced server-side
    rerender()
    expect(result.current.lastSeenEventId).toBe("e1") // frozen at arrival
  })

  test("ready is false and lastSeenEventId null until the query resolves", () => {
    queryData = undefined
    const { result } = renderHook(() => useWorkspaceViewState("ws-1", "me"))
    expect(result.current.ready).toBe(false)
    expect(result.current.lastSeenEventId).toBeNull()
  })
})
