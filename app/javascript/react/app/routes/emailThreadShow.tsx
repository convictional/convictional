import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { EmailThreadSkeleton } from "~/react/features/emailThreadShow/EmailThreadSkeleton"

import { shellRoute } from "../shellRoute"

// The email-thread conversation view. The document title, the re-sourced "back"
// affordance, and the request-access CTA are all handled in the component, since
// none is known until the GET /api/email_threads/{id} fetch resolves (see
// EmailThreadShow). Channels derive from the emailThreadId route param plus the
// fetched workspace_id, so the route passes no props.
const EmailThreadShowView = lazyRouteComponent(
  () => import("~/react/features/emailThreadShow/EmailThreadShow"),
  "EmailThreadShow"
)

// `return_to` carries the "back" target (the inbox, a search page, a gid redirect
// source); it feeds the client `back`. `mailbox_entry_id` is stamped onto the
// inbox→thread href by the mailbox list; the show component derives its mailbox
// entry server-side from the current user and doesn't read it, but it must be
// declared so a client navigation preserves it (TanStack drops undeclared search
// params).
export interface EmailThreadShowSearch {
  return_to?: string
  mailbox_entry_id?: string
}

export const emailThreadShowRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/email_threads/$emailThreadId",
  // Full-screen on mobile — suppress the top nav and its bottom offset, matching
  // the Jinja `mobile_nav_hidden` flag the page carried before cutover.
  // showGmailReauthBadge mirrors email_threads_show's membership in the legacy
  // GMAIL_REAUTH_BADGE_ROUTES list.
  staticData: { hideMobileNav: true, showGmailReauthBadge: true },
  validateSearch: (search: Record<string, unknown>): EmailThreadShowSearch => ({
    return_to: typeof search.return_to === "string" ? search.return_to : undefined,
    mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
  }),
  component: EmailThreadShowView,
  // A thread switch (e.g. the mailbox prev/next soft-nav) is a fresh conversation.
  // Remount the view on emailThreadId so every per-thread state field, ref,
  // subscription, and scroll cursor reinitializes — rather than hand-resetting
  // them across the component and its hooks. TanStack keeps a route component
  // mounted across param changes by default; remountDeps opts out for this route.
  remountDeps: ({ params }) => params.emailThreadId,
  // Paints while the lazy page chunk downloads, so opening a thread shows the
  // skeleton instantly — before the page code or its data exist.
  pendingComponent: EmailThreadSkeleton,
})
