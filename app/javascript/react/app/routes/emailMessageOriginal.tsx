import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { shellRoute } from "../shellRoute"

// The superuser "view original" message view. It reads its ids from the route
// params and fetches its own payload, so the route passes no props. No search
// params. The component renders its own loading state while the message fetches.
const EmailMessageOriginalView = lazyRouteComponent(
  () => import("~/react/features/emailMessageOriginal/EmailMessageOriginal"),
  "EmailMessageOriginal"
)

export const emailMessageOriginalRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/email_threads/$emailThreadId/email_messages/$emailMessageId",
  staticData: { hideMobileNav: true },
  component: EmailMessageOriginalView,
})
