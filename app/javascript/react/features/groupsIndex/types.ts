import type { PaginatedResponse, User } from "~/react/shared/types"

// Mirrors `app.routers.api.groups.GroupMemberResponse`.
export interface GroupMemberAvatar {
  id: string
  user: User
}

// Mirrors `app.routers.api.groups.GroupRowResponse`.
export interface GroupRow {
  id: string
  name: string
  member_count: number
  members: GroupMemberAvatar[]
  is_member: boolean
}

// Mirrors `app.routers.api.groups.GroupListResponse`.
export interface GroupListResponse extends PaginatedResponse {
  groups: GroupRow[]
}
