import type { GroupRow } from "~/react/features/groupsIndex/types"

export function makeGroup(overrides: Partial<GroupRow> = {}): GroupRow {
  return {
    id: "group-1",
    name: "Engineering",
    member_count: 2,
    members: [
      { id: "m1", user: { id: "u1", display_name: "Alice", picture: null } },
      { id: "m2", user: { id: "u2", display_name: "Bob", picture: null } },
    ],
    is_member: false,
    ...overrides,
  }
}
