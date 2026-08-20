import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import { redirectToHome } from "~/react/shared/routerGuards"
import { getCurrentUser } from "~/react/shared/stores/currentUser"

import { shellRoute } from "../shellRoute"

// Route definitions live in app/ and import features only as components; see
// docs/react-migration.md → "Conventions for the routing foundation and every page cutover".
const OrganizationSettingsView = lazyRouteComponent(
  () => import("~/react/features/organizationSettings/OrganizationSettings"),
  "OrganizationSettings"
)

function OrganizationSettingsPage() {
  useDocumentTitle("Edit Organization")
  return <OrganizationSettingsView />
}

export const organizationSettingsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/organization/edit",
  // Admin-only, replacing the server gate the old Jinja route carried
  // (include_router(organizations, Depends(get_admin_user))). The shell's
  // beforeLoad has already populated the currentUser cache, so this is a cheap
  // cache read; the /api/organization* endpoints stay admin-gated regardless.
  beforeLoad: async () => {
    const user = await getCurrentUser()
    if (!user.is_admin) redirectToHome()
  },
  component: OrganizationSettingsPage,
})
