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

// Minimal SPA shell router mirroring the real tree's shape: a pathless layout
// route with id "shell" parenting `/posts/$postId/edit` (the editor under test)
// and a `/posts/$postId` stub, so the published→show redirect has a destination
// to land on. The shell prefix matters — the editor reads params/search via
// getRouteApi("/shell/posts/$postId/edit"), so the ids must match. validateSearch
// mirrors the real routes so navigate()/useSearch() round-trip the same shape.
export function buildEditorRouter(editorComponent: ComponentType, initialEntries: string[] = ["/posts/p1/edit"]) {
  const rootRoute = createRootRoute()
  const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })
  const editorTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/posts/$postId/edit",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
      mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
    }),
    component: editorComponent,
  })
  const showTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/posts/$postId",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
      mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
    }),
    component: () => <div data-testid="show-page" />,
  })
  return createRouter({
    routeTree: rootRoute.addChildren([shellTestRoute.addChildren([editorTestRoute, showTestRoute])]),
    history: createMemoryHistory({ initialEntries }),
  })
}

export async function renderInEditorRouter(editorComponent: ComponentType, initialEntries?: string[]) {
  const router = buildEditorRouter(editorComponent, initialEntries)
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
