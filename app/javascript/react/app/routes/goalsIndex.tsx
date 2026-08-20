import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { GoalsListSkeleton } from "~/react/features/goalsIndex/GoalsListSkeleton"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"

import { shellRoute } from "../shellRoute"

// See documentsIndex.tsx for the route-definition conventions. lazyRouteComponent
// code-splits the page chunk while the route's contracts (validateSearch) stay eager.
const GoalsIndexView = lazyRouteComponent(() => import("~/react/features/goalsIndex/GoalsIndex"), "GoalsIndex")

// The index URL carries the view selector (`is_completed` / `is_closed` /
// `planning_list_name` — mutually exclusive, all absent meaning the active view)
// plus the owner/group filters. This preserves the legacy contract that
// url_for("goals_index") still produces server-side (global_ids.py's Goal and
// GoalComment gid redirects emit the three view params).
export interface GoalsIndexSearch {
  is_completed?: true
  is_closed?: true
  planning_list_name?: string
  owner_ids?: string[]
  group_ids?: string[]
}

// TanStack's read and write forms for repeated params are asymmetric: the URL
// parser collects `?owner_ids=a&owner_ids=b` into an array but leaves a lone
// `?owner_ids=a` a bare string, while navigate() writes an array as a
// JSON-stringified single value. All three forms must therefore round-trip, so
// old bookmarked repeated-key URLs keep working. (Fixing the write form would
// need a custom stringifySearch on createRouter, which is global and would
// change serialization for every existing route.)
function toIdArray(value: unknown): string[] | undefined {
  if (Array.isArray(value)) {
    const ids = value.filter((id): id is string => typeof id === "string" && !!id)
    return ids.length ? ids : undefined
  }
  if (typeof value === "string" && value) return [value]
  return undefined
}

function GoalsPage() {
  useDocumentTitle("Goals")
  return <GoalsIndexView />
}

export const goalsIndexRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/goals",
  validateSearch: (search: Record<string, unknown>): GoalsIndexSearch => ({
    // Search params arrive parsed (JSON) from the URL, so `?is_closed=true` is the
    // boolean true; tolerate the string form defensively. false normalizes out.
    is_completed: search.is_completed === true || search.is_completed === "true" ? true : undefined,
    is_closed: search.is_closed === true || search.is_closed === "true" ? true : undefined,
    // The parser coerces numeric-looking values, so a planning list literally
    // named "2026" arrives as a number — String() keeps it a name.
    planning_list_name:
      search.planning_list_name === undefined || search.planning_list_name === null || search.planning_list_name === ""
        ? undefined
        : String(search.planning_list_name),
    owner_ids: toIdArray(search.owner_ids),
    group_ids: toIdArray(search.group_ids),
  }),
  component: GoalsPage,
  // Paints while the lazy page chunk downloads, so the skeleton shows the instant
  // a <Link> lands here — before the page code or its data exist.
  pendingComponent: GoalsListSkeleton,
})
