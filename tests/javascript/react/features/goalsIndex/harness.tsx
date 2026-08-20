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

import { useGoalsData } from "~/react/features/goalsIndex/hooks/useGoalsData"

import { createTestQueryClient } from "../../shared/testUtils"

// Builds a minimal SPA shell router mirroring the real tree's shape: a pathless
// layout route with id "shell" parenting `/goals` and `/goals/$goalId`. The shell
// prefix matters — the feature reads search params via getRouteApi("/shell/goals"),
// so the ids must match. The show route is a stub so the index's row <Link>s have
// a destination to land on. validateSearch mirrors the real route so
// navigate()/useSearch() round-trip the same shape, including the three legacy
// read forms for the repeated array params.
export function buildGoalsRouter(indexComponent: ComponentType, initialEntries: string[] = ["/goals"]) {
  const rootRoute = createRootRoute()
  const shellTestRoute = createRoute({ getParentRoute: () => rootRoute, id: "shell", component: () => <Outlet /> })
  const goalsTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/goals",
    validateSearch: (search: Record<string, unknown>) => ({
      is_completed: search.is_completed === true || search.is_completed === "true" ? true : undefined,
      is_closed: search.is_closed === true || search.is_closed === "true" ? true : undefined,
      planning_list_name:
        search.planning_list_name === undefined ||
        search.planning_list_name === null ||
        search.planning_list_name === ""
          ? undefined
          : String(search.planning_list_name),
      owner_ids: toIdArray(search.owner_ids),
      group_ids: toIdArray(search.group_ids),
    }),
    component: indexComponent,
  })
  const goalShowTestRoute = createRoute({
    getParentRoute: () => shellTestRoute,
    path: "/goals/$goalId",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
      mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
    }),
    component: () => <div data-testid="show-page" />,
  })
  return createRouter({
    routeTree: rootRoute.addChildren([shellTestRoute.addChildren([goalsTestRoute, goalShowTestRoute])]),
    history: createMemoryHistory({ initialEntries }),
  })
}

function toIdArray(value: unknown): string[] | undefined {
  if (Array.isArray(value)) {
    const ids = value.filter((id): id is string => typeof id === "string" && !!id)
    return ids.length ? ids : undefined
  }
  if (typeof value === "string" && value) return [value]
  return undefined
}

// An isolated client per render (not the singleton) so one test's goal list
// cache can't paint in the next — the feature's queries are keyed only by
// view/filters, which every test shares.
export async function renderInGoalsRouter(indexComponent: ComponentType, initialEntries?: string[]) {
  const router = buildGoalsRouter(indexComponent, initialEntries)
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

// Renders useGoalsData as the /goals route component (so its getRouteApi/useNavigate
// calls resolve against a real router) and captures its return on every render. The
// view and filters live in the URL, so pass them via initialEntries
// (e.g. ["/goals?is_closed=true"]).
export async function renderGoalsDataHook(initialEntries?: string[]) {
  const captured: { current: ReturnType<typeof useGoalsData> } = { current: null as never }
  function Probe() {
    captured.current = useGoalsData()
    return null
  }
  const { router, client } = await renderInGoalsRouter(Probe, initialEntries)
  return { result: captured, router, client }
}
