import { createRootRoute, createRoute, createRouter, Outlet, RouterProvider } from "@tanstack/react-router"
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, test } from "vitest"

import { NavLink } from "~/react/shared/NavLink"

afterEach(cleanup)

// Build a minimal SPA shell: a root layout plus `/notifications` as the one
// registered client route. `/chats` is intentionally absent — it stands in for a
// path still served by Jinja. Uses the default browser history so jsdom keeps
// window.location in sync on client navigation, mirroring production.
async function renderInRouter(ui: ReactNode, initialPath = "/") {
  window.history.replaceState({}, "", initialPath)
  const rootRoute = createRootRoute({
    component: () => (
      <>
        {ui}
        <Outlet />
      </>
    ),
  })
  const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: () => null })
  const notificationsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/notifications",
    component: () => <div data-testid="notifications-page" />,
  })
  // A registered route that takes a search param, to exercise query passthrough.
  const documentsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/documents",
    validateSearch: (search: Record<string, unknown>) => ({
      filter: typeof search.filter === "string" ? search.filter : undefined,
    }),
    component: () => <div data-testid="documents-page" />,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, notificationsRoute, documentsRoute]),
  })
  const result = render(<RouterProvider router={router} />)
  // RouterProvider resolves the initial match in an effect; flush it so the
  // route subtree (and the NavLink under test) is mounted before assertions.
  await act(async () => {
    await router.load()
  })
  return { router, ...result }
}

describe("NavLink", () => {
  describe("island mode (no router context)", () => {
    test("renders a plain anchor; prefetch adds the htmx preload attribute", () => {
      render(
        <NavLink href="/chats" prefetch data-hotkey="g c">
          Chat
        </NavLink>
      )
      const link = screen.getByRole("link", { name: "Chat" })
      expect(link).toHaveAttribute("href", "/chats")
      expect(link).toHaveAttribute("preload", "mouseover")
      expect(link).toHaveAttribute("data-hotkey", "g c")
    })

    test("omits the preload attribute without prefetch", () => {
      render(<NavLink href="/groups">Groups</NavLink>)
      const link = screen.getByRole("link", { name: "Groups" })
      expect(link).toHaveAttribute("href", "/groups")
      expect(link).not.toHaveAttribute("preload")
    })

    test("clientRouted opts out of boosting and skips the wasted hover preload", () => {
      render(
        <NavLink href="/documents" prefetch clientRouted>
          Docs
        </NavLink>
      )
      const link = screen.getByRole("link", { name: "Docs" })
      // hx-boost="false" keeps the click a native load of the SPA shell; with no
      // boosted fetch, the hover preload would only warm an unused 204, so it's
      // dropped even though prefetch is set.
      expect(link).toHaveAttribute("hx-boost", "false")
      expect(link).not.toHaveAttribute("preload")
    })
  })

  describe("shell mode (inside a router)", () => {
    test("registered path becomes a client link: click navigates without a document load", async () => {
      const { router } = await renderInRouter(<NavLink href="/notifications">Notifications</NavLink>, "/")
      const link = screen.getByRole("link", { name: "Notifications" })

      // TanStack intercepts the click and prevents the default full-document load.
      const event = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 })
      act(() => {
        link.dispatchEvent(event)
      })
      expect(event.defaultPrevented).toBe(true)
      expect(router.latestLocation.pathname).toBe("/notifications")
    })

    test("registered path with a query string client-navigates and carries the search", async () => {
      const { router } = await renderInRouter(<NavLink href="/documents?filter=anyone">Docs</NavLink>, "/")
      const link = screen.getByRole("link", { name: "Docs" })

      const event = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 })
      act(() => {
        link.dispatchEvent(event)
      })
      // The query didn't force a full-document load; it rode the client navigation.
      expect(event.defaultPrevented).toBe(true)
      expect(router.latestLocation.pathname).toBe("/documents")
      expect(router.latestLocation.search).toMatchObject({ filter: "anyone" })
    })

    test("registered client link never carries the htmx preload attribute", async () => {
      await renderInRouter(
        <NavLink href="/notifications" prefetch>
          Notifications
        </NavLink>,
        "/"
      )
      const link = screen.getByRole("link", { name: "Notifications" })
      expect(link).not.toHaveAttribute("preload")
    })

    test("clientRouted carries no hx-boost in the shell: the client <Link> already owns navigation", async () => {
      await renderInRouter(
        <NavLink href="/documents" prefetch clientRouted>
          Docs
        </NavLink>,
        "/"
      )
      const link = screen.getByRole("link", { name: "Docs" })
      expect(link).not.toHaveAttribute("hx-boost")
    })

    test("unregistered path stays a full-document anchor: click is not intercepted", async () => {
      const { router } = await renderInRouter(
        <NavLink href="/chats" prefetch>
          Chat
        </NavLink>,
        "/"
      )
      const link = screen.getByRole("link", { name: "Chat" })
      expect(link).toHaveAttribute("href", "/chats")
      // No htmx in the shell and no client route to prefetch.
      expect(link).not.toHaveAttribute("preload")

      const event = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 })
      act(() => {
        link.dispatchEvent(event)
      })
      expect(event.defaultPrevented).toBe(false)
      expect(router.latestLocation.pathname).toBe("/")
    })
  })
})
