import { createRootRoute, createRoute, Outlet } from "@tanstack/react-router"
import { lazy, Suspense } from "react"

import { AppShell } from "./AppShell"
import { loadShellBootstrap } from "./shellBootstrap"

// The root and authenticated-shell layout routes live here, apart from router.tsx
// (which composes the tree and owns the router instance), so route modules in
// routes/ can reference shellRoute as their parent without a router.tsx ↔ routes/
// import cycle (the no-circular dependency-cruiser rule).

// Lazy + prod-gated so the devtools never enter the production bundle (the dead
// branch is eliminated when import.meta.env.PROD is statically true). Hidden by
// default in development too, since the overlay obscures bottom-anchored UI like
// the mobile composer; set VITE_ROUTER_DEVTOOLS=true (e.g. in a gitignored
// .env.development.local) to show it.
const RouterDevtools =
  import.meta.env.PROD || import.meta.env.VITE_ROUTER_DEVTOOLS !== "true"
    ? () => null
    : lazy(() => import("@tanstack/react-router-devtools").then(m => ({ default: m.TanStackRouterDevtools })))

function RootComponent() {
  return (
    <>
      <Outlet />
      <Suspense>
        <RouterDevtools />
      </Suspense>
    </>
  )
}

export const rootRoute = createRootRoute({
  component: RootComponent,
})

// Pathless layout route: the authenticated AppShell (nav + chrome). Its
// beforeLoad fetches the bootstrap payload and applies the login guard
// before any nested page renders. Pages register as its children in
// router.tsx's tree composition.
export const shellRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "shell",
  beforeLoad: ({ location }) => loadShellBootstrap(location.href),
  component: AppShell,
})
