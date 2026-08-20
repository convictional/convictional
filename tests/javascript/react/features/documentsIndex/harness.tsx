import { QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { act, render as rtlRender } from "@testing-library/react"
import type { ComponentType } from "react"

import { createTestQueryClient } from "../../shared/testUtils"

// Builds a minimal SPA shell router that mirrors the real route tree's shape:
// a pathless layout route with id "shell" parenting `/documents` and
// `/documents/$documentId`. The shell prefix matters — the feature reads search
// params via getRouteApi("/shell/documents"), so the ids must match. The
// detail route is a stub so navigation has a destination to land on.
export function buildDocumentsRouter(indexComponent: ComponentType, initialEntries: string[] = ["/documents"]) {
  const rootRoute = createRootRoute()
  const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })
  const documentsTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/documents",
    validateSearch: (search: Record<string, unknown>) => ({
      filter: search.filter === "anyone" || search.filter === "others" ? search.filter : undefined,
      q: typeof search.q === "string" && search.q ? search.q : undefined,
    }),
    component: indexComponent,
  })
  const documentShowTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/documents/$documentId",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
    }),
    component: () => <div data-testid="show-page" />,
  })
  // "New document" navigates client-side to the editor, so the tree needs a real
  // edit destination (a stub reflecting its documentId param).
  const documentEditTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/documents/$documentId/edit",
    component: function EditStub() {
      const { documentId } = documentEditTestRoute.useParams()
      return <div data-testid="edit-page" data-document-id={documentId} />
    },
  })
  return createRouter({
    routeTree: rootRoute.addChildren([
      shellTestRoute.addChildren([documentsTestRoute, documentShowTestRoute, documentEditTestRoute]),
    ]),
    history: createMemoryHistory({ initialEntries }),
  })
}

export async function renderInDocumentsRouter(indexComponent: ComponentType, initialEntries?: string[]) {
  const router = buildDocumentsRouter(indexComponent, initialEntries)
  const client = createTestQueryClient()
  const utils = rtlRender(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  // RouterProvider resolves the initial match in an effect; flush it so the page
  // subtree is mounted before assertions.
  await act(async () => {
    await router.load()
  })
  return { router, client, ...utils }
}
