import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { DocumentShowSkeleton } from "~/react/features/documentShow/DocumentShowSkeleton"

import { shellRoute } from "../shellRoute"

// Read-only document view. The collaborator→editor redirect and the document
// title are both handled in the component, since neither is known until the
// detail query resolves (see DocumentShow).
const DocumentShowView = lazyRouteComponent(() => import("~/react/features/documentShow/DocumentShow"), "DocumentShow")

// `return_to` carries the "back" target (the index, a search page, a gid
// redirect source).
export interface DocumentShowSearch {
  return_to?: string
}

export const documentShowRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/documents/$documentId",
  staticData: { hideMobileNav: true },
  validateSearch: (search: Record<string, unknown>): DocumentShowSearch => ({
    return_to: typeof search.return_to === "string" ? search.return_to : undefined,
  }),
  component: DocumentShowView,
  // Paints while the lazy page chunk downloads, so clicking a document row shows
  // the skeleton instantly — before the page code or its data exist.
  pendingComponent: DocumentShowSkeleton,
})
