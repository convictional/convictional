import { redirect } from "@tanstack/react-router"

import { withRedirectTo } from "~/react/shared/returnTo"

// beforeLoad guards for client routes (see docs/react-migration.md → Client-Side
// Router ADR). /login is still a server-rendered Jinja page, so that one forces a
// full-document load with `reloadDocument`. (TanStack only auto-infers that for an
// *absolute* href; a relative href like "/login?..." would otherwise be treated as
// a client route and land on the not-found component.)

// Unauthenticated → /login, carrying the current location via the server's
// `redirect_to` post-auth contract (mirrors remember_location()). This is the
// router-redirect counterpart to apiFetch's 401 handling, so a loader that hits
// a 401 and a beforeLoad that knows the user is anonymous both land here.
export function redirectToLogin(): never {
  throw redirect({ href: withRedirectTo("/login"), reloadDocument: true })
}

// Authenticated but not permitted → home. The client counterpart to the server's
// get_admin_user 403 for admin-only pages: rather than render a dead-end error,
// send the user somewhere usable. The inbox is a client route, so this stays a soft
// navigation — a permission bounce shouldn't tear down the realm.
export function redirectToHome(): never {
  throw redirect({ to: "/" })
}
