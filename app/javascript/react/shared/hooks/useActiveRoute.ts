import { useCallback, useSyncExternalStore } from "react"

import { useOptionalRouter } from "~/react/shared/hooks/useOptionalRouter"

// Returns the current pathname, kept fresh in both worlds the nav renders in.
// Both the subscription source and the snapshot are chosen by router context so
// hooks stay unconditional (one useSyncExternalStore call either way):
//
// - Shell mode (inside a RouterProvider): subscribe to the router's history and
//   read the router's own `latestLocation`. Client navigations push state without
//   firing `popstate`, so the htmx/popstate listeners would miss them; and there's
//   no htmx in the shell, so the `htmx:afterSettle` listener must not be registered
//   at all. We must NOT read window.location here: TanStack's browser history
//   defers the real history.pushState to a microtask while notifying subscribers
//   synchronously, so window.location is stale when our callback fires (and no
//   further event re-fires), which would leave the active tab a navigation behind.
//   `latestLocation` is updated synchronously from the history before notify.
// - Island mode (legacy Jinja pages): track `popstate` (back/forward) and
//   `htmx:afterSettle` (hx-boost navigations, which fire after history.pushState
//   so window.location is already updated), reading window.location.pathname.
export function useActiveRoute(): string {
  const router = useOptionalRouter()

  const subscribe = useCallback(
    (onChange: () => void) => {
      if (router) return router.history.subscribe(onChange)

      window.addEventListener("popstate", onChange)
      document.addEventListener("htmx:afterSettle", onChange)
      return () => {
        window.removeEventListener("popstate", onChange)
        document.removeEventListener("htmx:afterSettle", onChange)
      }
    },
    [router]
  )

  return useSyncExternalStore(
    subscribe,
    () => {
      if (router) return router.latestLocation.pathname
      return typeof window === "undefined" ? "/" : window.location.pathname
    },
    () => "/"
  )
}
