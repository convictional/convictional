import { createRouter } from "@tanstack/react-router"

import { chatsIndexRoute } from "./routes/chats"
import { chatShowRoute } from "./routes/chatShow"
import { documentEditRoute } from "./routes/documentEdit"
import { documentShowRoute } from "./routes/documentShow"
import { documentsIndexRoute } from "./routes/documentsIndex"
import { emailMessageOriginalRoute } from "./routes/emailMessageOriginal"
import { emailThreadShowRoute } from "./routes/emailThreadShow"
import { goalShowRoute } from "./routes/goalShow"
import { goalsIndexRoute } from "./routes/goalsIndex"
import {
  mailboxArchivedRoute,
  mailboxAssignedToMeRoute,
  mailboxDraftsRoute,
  mailboxIndexRoute,
  mailboxSentRoute,
  mailboxSnoozedRoute,
  mailboxUnreadRoute,
} from "./routes/mailboxIndex"
import { notificationsRoute } from "./routes/notifications"
import { organizationSettingsRoute } from "./routes/organizationSettings"
import { postDraftEditorRoute } from "./routes/postDraftEditor"
import { postShowRoute } from "./routes/postShow"
import { postsIndexRoute } from "./routes/postsIndex"
import { rootRoute, shellRoute } from "./shellRoute"

// The client-routed top layer (see docs/react-migration.md → Client-Side Router
// ADR). This module composes the route tree and owns the router instance. Route
// definitions live in routes/ (each importing shellRoute as its parent); the
// root/shell layout routes live in shellRoute.tsx. Features never import any of
// this — they get typed `<Link to>`, `useNavigate()`, and `getRouteApi('/path')`
// purely from the `Register` augmentation below, which keeps the one-way
// `features → composites → shared → ui` layering intact (the `app-is-the-top`
// dependency-cruiser rule seals `react/app/` from below).

// An unmatched path falls through to NotFoundComponent — the signal that the
// shell was served for a path with no registered client route. Routes override
// it with their own boundary. (Render errors are caught by the IslandErrorBoundary
// the SPA entry wraps the router in, which also reports to Sentry.)
function NotFoundComponent() {
  return null
}

// Code-based route tree, composed manually (not file-based) — fits the
// single-entry Vite build. Add a route by importing it from routes/ and nesting
// it under the shell here.
const routeTree = rootRoute.addChildren([
  shellRoute.addChildren([
    mailboxIndexRoute,
    mailboxUnreadRoute,
    mailboxArchivedRoute,
    mailboxSentRoute,
    mailboxDraftsRoute,
    mailboxAssignedToMeRoute,
    mailboxSnoozedRoute,
    notificationsRoute,
    organizationSettingsRoute,
    documentsIndexRoute,
    documentShowRoute,
    documentEditRoute,
    postsIndexRoute,
    postShowRoute,
    postDraftEditorRoute,
    goalsIndexRoute,
    goalShowRoute,
    chatsIndexRoute,
    chatShowRoute,
    emailThreadShowRoute,
    emailMessageOriginalRoute,
  ]),
])

export const router = createRouter({
  routeTree,
  // TanStack's built-in scroll restoration is the SPA's scroll source.
  scrollRestoration: true,
  // Preload a route's lazy chunk (and later its loader) on hover/focus intent,
  // so migrated pages feel snappy.
  defaultPreload: "intent",
  defaultNotFoundComponent: NotFoundComponent,
})

// Features import bare `@tanstack/react-router` and get full route type-safety
// from this augmentation without ever importing the tree.
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
