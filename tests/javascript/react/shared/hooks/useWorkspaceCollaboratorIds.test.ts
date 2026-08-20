import { renderHook } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"

import type { WorkspaceCollaboratorsData } from "~/react/shared/types"

// useWorkspaceCollaboratorIds is a thin selector over the shared collaborators query; the
// fetch/dedup/channel plumbing lives in (and is tested via) useWorkspaceCollaboratorsQuery.
let queryData: WorkspaceCollaboratorsData | undefined
vi.mock("~/react/shared/hooks/useWorkspaceCollaboratorsQuery", () => ({
  useWorkspaceCollaboratorsQuery: () => ({ data: queryData }),
}))

import { useWorkspaceCollaboratorIds } from "~/react/shared/hooks/useWorkspaceCollaboratorIds"

function data(ids: string[]): WorkspaceCollaboratorsData {
  return {
    collaborators: ids.map(id => ({
      id: `c-${id}`,
      user: { id, display_name: id, picture: null },
      is_removable: true,
      status: "approved" as const,
      view_state: { viewed: false, last_viewed_at: null, last_viewed_event_id: null },
    })),
    pending: [],
    viewers: [],
    present_user_ids: [],
    current_user_view_state: { viewed: false, last_viewed_at: null, last_viewed_event_id: null },
  }
}

describe("useWorkspaceCollaboratorIds", () => {
  test("maps the cached collaborators to a set of user ids", () => {
    queryData = data(["u1", "u2"])
    const { result } = renderHook(() => useWorkspaceCollaboratorIds("ws-1"))
    expect(result.current).toEqual(new Set(["u1", "u2"]))
  })

  test("returns undefined until the query has data (org-wide fallback)", () => {
    queryData = undefined
    const { result } = renderHook(() => useWorkspaceCollaboratorIds("ws-1"))
    expect(result.current).toBeUndefined()
  })
})
