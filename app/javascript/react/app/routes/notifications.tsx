import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"

import { shellRoute } from "../shellRoute"

// Route definitions live in app/ and import features only as components; see
// docs/react-migration.md → "Conventions for the routing foundation and every page cutover".
// lazyRouteComponent code-splits the page chunk while the route's contracts stay eager.
const NotificationsView = lazyRouteComponent(
  () => import("~/react/features/notifications/Notifications"),
  "Notifications"
)

function NotificationsPage() {
  useDocumentTitle("Notifications")
  return <NotificationsView />
}

export const notificationsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/notifications",
  component: NotificationsPage,
})
