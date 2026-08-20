import {
  type ClientConfig,
  type CurrentUser,
  type CurrentUserApiResponse,
  type CurrentUserData,
  currentUserQueryKey,
} from "~/react/shared/stores/currentUser"
import { queryClient } from "~/react/shared/queryClient"

// One definition of the viewer's field list, so tests don't each re-list the
// CurrentUser shape and drift silently when the type gains a field.
export function buildCurrentUser(overrides: Partial<CurrentUser> & { id: string }): CurrentUser {
  return {
    display_name: "Viewer",
    email: "viewer@example.com",
    is_superuser: false,
    is_admin: false,
    picture: null,
    organization_id: "org-1",
    organization_name: null,
    time_zone: null,
    feedback_upload_url: "/api/workspaces/attachments",
    ...overrides,
  }
}

// The raw /api/users/me payload, before useCurrentUser splits client_config and
// flashes out of the cached CurrentUserData. Use to mock apiFetch on a cold load.
export function buildCurrentUserApiResponse(overrides: Partial<CurrentUser> & { id: string }): CurrentUserApiResponse {
  return { ...buildCurrentUser(overrides), client_config: { klipy_api_key: null }, flashes: [] }
}

// Seed the singleton currentUser query cache with a loaded viewer. Tests render
// through the singleton-backed render() in testUtils, so useCurrentUser() reads
// this without firing a /api/users/me fetch.
export function setCurrentUser(
  overrides: Partial<CurrentUser> & { id: string },
  clientConfig: ClientConfig = { klipy_api_key: null }
) {
  const data: CurrentUserData = {
    user: buildCurrentUser(overrides),
    clientConfig,
  }
  queryClient.setQueryData(currentUserQueryKey, data)
}

export function resetCurrentUser() {
  queryClient.removeQueries({ queryKey: currentUserQueryKey })
}
