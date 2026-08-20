import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { shellRoute } from "../shellRoute"

// The collaborative editor. The document title, the re-sourced props (upload
// URL, subscription bell, current user), and the non-collaborator→show redirect
// are all handled in the component, since none is known until the detail query
// resolves (see DocumentEditor). Channels derive from the document_id route
// param alone, so the route passes no props.
const DocumentEditorView = lazyRouteComponent(
  () => import("~/react/features/documentEditor/DocumentEditor"),
  "DocumentEditor"
)

// `return_to` carries the "back" target (the index, a search page, a gid
// redirect source), mirroring documentShow.
export interface DocumentEditSearch {
  return_to?: string
}

export const documentEditRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/documents/$documentId/edit",
  // The editor's comment gutter is positioned beyond the content column; clip the
  // shell #container's horizontal overflow so it doesn't induce page-level scroll.
  staticData: { clipContainerOverflowX: true, hideMobileNav: true },
  validateSearch: (search: Record<string, unknown>): DocumentEditSearch => ({
    return_to: typeof search.return_to === "string" ? search.return_to : undefined,
  }),
  component: DocumentEditorView,
})
