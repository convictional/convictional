import type { Group, PaginatedResponse } from "~/react/shared/types"

// Mirrors `app.routers.api.schemas.OrganizationUserResponse`. A member's top
// goal is intentionally *not* embedded here — it's its own resource, surfaced
// lazily on the row's UserHoverCard (which fetches GET /api/users/{id}/top_goal).
export interface OrganizationUser {
  id: string
  display_name: string
  picture: string | null
  email: string
  bio: string | null
  is_admin: boolean
  // Explicit positive lifecycle state (not is_deleted). Deactivated members
  // still exist and are restorable, so the client tabs on this flag.
  active: boolean
  groups: Group[]
}

// Mirrors `app.routers.api.schemas.OrganizationUsersListResponse`.
export interface OrganizationUsersListResponse extends PaginatedResponse {
  users: OrganizationUser[]
}
