import { type QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterContextProvider,
  RouterProvider,
} from "@tanstack/react-router"
import { act, render as rtlRender } from "@testing-library/react"
import type { ReactElement, ReactNode } from "react"

import { queryClient } from "~/react/shared/queryClient"

// Builds a minimal SPA shell router mirroring the real tree's shape: a pathless
// layout route with id "shell" parenting the seven inbox paths plus stub show
// routes for the four entry types.
//
// All seven inbox routes render the same node, as they do in production — one page
// distinguished by which view it reads. The page under test is passed as an element
// rather than a component because these suites drive it through explicit props
// (view, focus selector); `initialEntries` only decides which path it mounts on, so
// <Link to="/unread"> and the sort links have somewhere to resolve.
//
// The show routes are stubs so entry-row <Link>s have a destination. validateSearch
// mirrors the real routes so navigate()/useSearch() round-trip the same shape.
// The page under test varies per render, so the inbox routes read it from here
// rather than closing over it — which lets the route tree be built once per module
// instead of once per render. Safe because tests within a file run sequentially.
const currentPage: { node: ReactNode } = { node: null }

const rootRoute = createRootRoute()
const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })

const routeTree = (() => {
  const focusSearch = (search: Record<string, unknown>) => ({
    mailbox_view_id: typeof search.mailbox_view_id === "string" ? search.mailbox_view_id : undefined,
    mailbox_view_template: typeof search.mailbox_view_template === "string" ? search.mailbox_view_template : undefined,
    goal_id: typeof search.goal_id === "string" ? search.goal_id : undefined,
  })

  const inboxRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/",
    validateSearch: (search: Record<string, unknown>) => ({
      ...focusSearch(search),
      sort: search.sort === "oldest" || search.sort === "newest" ? search.sort : undefined,
    }),
    component: () => currentPage.node,
  })
  const subViewRoutes = ["/unread", "/archived", "/sent", "/drafts", "/assigned_to_me", "/snoozed"].map(path =>
    createRoute({
      getParentRoute: () => shellTestRoute,
      path,
      validateSearch: focusSearch,
      component: () => currentPage.node,
    })
  )

  const entrySearch = (search: Record<string, unknown>) => ({
    return_to: typeof search.return_to === "string" ? search.return_to : undefined,
    mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
  })
  const showRoutes = ["/chats/$chatId", "/email_threads/$emailThreadId", "/posts/$postId", "/goals/$goalId"].map(
    path =>
      createRoute({
        getParentRoute: () => shellTestRoute,
        path,
        validateSearch: entrySearch,
        component: () => <div data-testid="show-page" />,
      })
  )
  // WelcomeShow links here from the onboarding focus.
  const organizationEditRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/organization/edit",
    component: () => <div data-testid="organization-edit-page" />,
  })

  return rootRoute.addChildren([
    shellTestRoute.addChildren([inboxRoute, ...subViewRoutes, ...showRoutes, organizationEditRoute]),
  ])
})()

function buildMailboxRouter(page: ReactNode, initialEntries: string[]) {
  currentPage.node = page
  return createRouter({ routeTree, history: createMemoryHistory({ initialEntries }) })
}

// Renders the inbox page inside a router and a query client.
//
// Defaults to the `queryClient` singleton, which is what production mounts against
// and what the view-mode suites seed and clear directly (queryClient.clear() in
// beforeEach, setQueryData to prime view state) — a private client would leave them
// driving a cache the component doesn't read. The hotkey suites want the opposite
// and pass their own, since a cached entries query from a prior test in the same
// file would otherwise shadow their fetch mock.
export async function renderInMailboxRouter(
  page: ReactNode,
  { initialEntries = ["/"], client = queryClient }: { initialEntries?: string[]; client?: QueryClient } = {}
) {
  const router = buildMailboxRouter(page, initialEntries)
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

// Router context without route rendering, for suites that mount a single component
// rather than the page. <Link> and useNavigate get what they need, while the
// component stays ordinary children — so testing-library's `rerender` keeps working,
// which RouterProvider (it renders the matched route, not children) would break.
export function renderWithMailboxRouterContext(ui: ReactElement, client: QueryClient = queryClient) {
  const router = buildMailboxRouter(null, ["/"])
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <RouterContextProvider router={router}>{children}</RouterContextProvider>
      </QueryClientProvider>
    )
  }
  return { router, ...rtlRender(ui, { wrapper: Wrapper }) }
}
