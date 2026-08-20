import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { DocumentsIndexSkeleton } from "~/react/features/documentsIndex/DocumentsIndexSkeleton"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import type { DocumentFilter } from "~/react/shared/types"

import { shellRoute } from "../shellRoute"

// See notifications.tsx for the route-definition conventions. lazyRouteComponent
// code-splits the page chunk while the route's contracts (validateSearch) stay eager.
const DocumentsIndexView = lazyRouteComponent(
  () => import("~/react/features/documentsIndex/DocumentsIndex"),
  "DocumentsIndex"
)

// The index URL carries two independent params: the browse-scope `filter` and a
// full-text `q`. `mine` is the default scope, so it's normalized out of the URL
// (absent === "mine"); an unknown filter falls back to absent rather than erroring.
export interface DocumentsIndexSearch {
  filter?: DocumentFilter
  q?: string
}

function isFilter(value: unknown): value is DocumentFilter {
  return value === "anyone" || value === "mine" || value === "others"
}

function DocumentsPage() {
  useDocumentTitle("Documents")
  return <DocumentsIndexView />
}

export const documentsIndexRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/documents",
  validateSearch: (search: Record<string, unknown>): DocumentsIndexSearch => ({
    filter: isFilter(search.filter) && search.filter !== "mine" ? search.filter : undefined,
    q: typeof search.q === "string" && search.q ? search.q : undefined,
  }),
  component: DocumentsPage,
  // Paints while the lazy page chunk downloads, so the skeleton shows the instant
  // a <Link> lands here — before the page code or its data exist.
  pendingComponent: DocumentsIndexSkeleton,
})
