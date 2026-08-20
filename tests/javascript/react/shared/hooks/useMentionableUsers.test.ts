import { renderHook } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"

const orgUsers = [
  { id: "me", display_name: "Me" },
  { id: "u1", display_name: "Alice" },
  { id: "u2", display_name: "Bob" },
]

vi.mock("~/react/shared/hooks/useOrganizationMembers", () => ({
  useOrganizationMembers: () => ({ users: orgUsers, groups: [], loading: false, error: null }),
}))

import { useMentionableUsers } from "~/react/shared/hooks/useMentionableUsers"

describe("useMentionableUsers", () => {
  test("includes the current user — you can mention yourself", () => {
    const { result } = renderHook(() => useMentionableUsers())
    expect(result.current.map(u => u.id)).toEqual(["me", "u1", "u2"])
  })

  test("without collaboratorIds, nobody is flagged (org-wide, no Collaborators split)", () => {
    const { result } = renderHook(() => useMentionableUsers())
    expect(result.current.every(u => !u.is_collaborator)).toBe(true)
  })

  test("with collaboratorIds, only those members are flagged as collaborators", () => {
    const { result } = renderHook(() => useMentionableUsers({ collaboratorIds: new Set(["me", "u1"]) }))
    expect(result.current).toEqual([
      { id: "me", display_name: "Me", is_collaborator: true },
      { id: "u1", display_name: "Alice", is_collaborator: true },
      { id: "u2", display_name: "Bob", is_collaborator: false },
    ])
  })
})
