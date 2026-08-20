import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { GoalShowSkeleton } from "~/react/features/goalShow/GoalShowSkeleton"

import { shellRoute } from "../shellRoute"
import { backAndMailboxSearch } from "./mailboxEntryHelpers"

// The goal detail page: header pickers, inline title/description editing, and the
// activity timeline. The document title is set in the component, since the goal's
// title isn't known until GET /api/goals/{id} resolves.
const GoalShowView = lazyRouteComponent(() => import("~/react/features/goalShow/GoalShow"), "GoalShow")

// `return_to` carries the "back" target (the index, a gid redirect source);
// `mailbox_entry_id` scopes the header's mailbox variant when the goal was opened
// from the inbox.
export const goalShowRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/goals/$goalId",
  staticData: { hideMobileNav: true },
  validateSearch: backAndMailboxSearch,
  component: GoalShowView,
  // Paints while the lazy page chunk downloads, so clicking a goal row shows the
  // skeleton instantly — before the page code or its data exist.
  pendingComponent: GoalShowSkeleton,
})
