import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from "../../../../app/javascript/react/shared/apiFetch"
import { queryClient } from "../../../../app/javascript/react/shared/queryClient"
import {
  getOrganizationMembers,
  organizationMembersQueryKey,
} from "../../../../app/javascript/react/shared/stores/organizationMembers"

const mockApiFetch = vi.mocked(apiFetch)

const response = {
  users: [{ id: "u1", display_name: "Alice", picture: null }],
  groups: [{ id: "g1", name: "Eng" }],
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(() => {
  // The imperative accessor reads/writes the singleton cache; clear it so cached
  // members don't leak across cases.
  queryClient.clear()
  vi.clearAllMocks()
})

describe("getOrganizationMembers", () => {
  test("fetches once on a cold cache and populates it", async () => {
    mockApiFetch.mockResolvedValueOnce(response)

    const members = await getOrganizationMembers()

    expect(members).toEqual({ users: response.users, groups: response.groups })
    expect(mockApiFetch).toHaveBeenCalledWith("/api/organization/members")
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(queryClient.getQueryData(organizationMembersQueryKey)).toEqual(members)
  })

  test("concurrent calls share one in-flight fetch (dedup)", async () => {
    mockApiFetch.mockResolvedValueOnce(response)

    const [a, b] = await Promise.all([getOrganizationMembers(), getOrganizationMembers()])

    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(a).toEqual(b)
  })

  test("returns the cached value without fetching once warm", async () => {
    mockApiFetch.mockResolvedValueOnce(response)
    await getOrganizationMembers()
    mockApiFetch.mockClear()

    const members = await getOrganizationMembers()

    expect(mockApiFetch).not.toHaveBeenCalled()
    expect(members.users[0].id).toBe("u1")
  })
})
