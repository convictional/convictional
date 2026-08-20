import { queryClient } from "~/react/shared/queryClient"
import {
  type OrganizationMembers,
  organizationMembersQueryKey,
} from "~/react/shared/stores/organizationMembers"

// Seed the singleton organizationMembers query cache with loaded members. Tests
// render through the singleton-backed render() in testUtils, so
// useOrganizationMembers() reads this without firing a /api/organization/members
// fetch — the cache replaces the old organizationMembersStore.setState seeding.
export function setOrganizationMembers(members: Partial<OrganizationMembers> = {}) {
  queryClient.setQueryData(organizationMembersQueryKey, {
    users: members.users ?? [],
    groups: members.groups ?? [],
  })
}

export function resetOrganizationMembers() {
  queryClient.removeQueries({ queryKey: organizationMembersQueryKey })
}
