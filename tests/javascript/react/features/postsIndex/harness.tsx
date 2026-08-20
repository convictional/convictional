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

import { usePostsData } from "~/react/features/postsIndex/hooks/usePostsData"

import { createTestQueryClient } from "../../shared/testUtils"

// Builds a minimal SPA shell router mirroring the real tree's shape: a pathless
// layout route with id "shell" parenting `/posts`, `/posts/$postId`, and
// `/posts/$postId/edit`. The shell prefix matters — the feature reads search
// params via getRouteApi("/shell/posts"), so the ids must match. The show/edit
// routes are stubs so the index's <Link>s (post cards → show, draft cards →
// editor) and the filter changers' navigations have a destination to land on.
// validateSearch mirrors the real routes so navigate()/useSearch() round-trip the
// same shape.
export function buildPostsRouter(indexComponent: ComponentType, initialEntries: string[] = ["/posts"]) {
  const rootRoute = createRootRoute()
  const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })
  const postsTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/posts",
    validateSearch: (search: Record<string, unknown>) => ({
      status: search.status === "drafts" ? "drafts" : undefined,
      group_id: typeof search.group_id === "string" && search.group_id ? search.group_id : undefined,
      decided: search.decided === true || search.decided === "true" ? true : undefined,
      q: typeof search.q === "string" && search.q ? search.q : undefined,
    }),
    component: indexComponent,
  })
  const postShowTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/posts/$postId",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
      mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
    }),
    component: () => <div data-testid="show-page" />,
  })
  const postEditTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/posts/$postId/edit",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
      mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
    }),
    component: () => <div data-testid="edit-page" />,
  })
  return createRouter({
    routeTree: rootRoute.addChildren([
      shellTestRoute.addChildren([postsTestRoute, postShowTestRoute, postEditTestRoute]),
    ]),
    history: createMemoryHistory({ initialEntries }),
  })
}

export async function renderInPostsRouter(indexComponent: ComponentType, initialEntries?: string[]) {
  const router = buildPostsRouter(indexComponent, initialEntries)
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

// Renders usePostsData as the /posts route component (so its getRouteApi/useNavigate
// calls resolve against a real router) and captures its return on every render. The
// filters live in the URL, so pass them via initialEntries (e.g. ["/posts?group_id=g1"]).
export async function renderPostsDataHook(initialEntries?: string[]) {
  const captured: { current: ReturnType<typeof usePostsData> } = { current: null as never }
  function Probe() {
    captured.current = usePostsData()
    return null
  }
  const { router } = await renderInPostsRouter(Probe, initialEntries)
  return { result: captured, router }
}
