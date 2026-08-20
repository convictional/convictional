import { createRootRoute, createRoute, createRouter, Outlet, RouterProvider } from "@tanstack/react-router"
import { act, cleanup, render, screen } from "@testing-library/react"
import { createElement, type ReactNode } from "react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { useActiveRoute } from "~/react/shared/hooks/useActiveRoute"

afterEach(cleanup)

function Probe() {
  return createElement("div", { "data-testid": "path" }, useActiveRoute())
}

function path(): string | null {
  return screen.getByTestId("path").textContent
}

// Mirrors NavLink.test's harness: a root layout that renders `children`, with
// `/notifications` registered. Default browser history keeps window.location in
// sync on client navigation (the snapshot source).
async function renderInRouter(children: ReactNode, initialPath = "/") {
  window.history.replaceState({}, "", initialPath)
  const rootRoute = createRootRoute({ component: () => createElement(Outlet) })
  const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: () => children })
  const notificationsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/notifications",
    component: () => children,
  })
  const router = createRouter({ routeTree: rootRoute.addChildren([indexRoute, notificationsRoute]) })
  const result = render(createElement(RouterProvider, { router }))
  await act(async () => {
    await router.load()
  })
  return { router, ...result }
}

describe("useActiveRoute", () => {
  describe("island mode (no router)", () => {
    test("tracks popstate and htmx:afterSettle", () => {
      window.history.replaceState({}, "", "/")
      render(createElement(Probe))
      expect(path()).toBe("/")

      act(() => {
        window.history.replaceState({}, "", "/posts/123")
        window.dispatchEvent(new PopStateEvent("popstate"))
      })
      expect(path()).toBe("/posts/123")

      act(() => {
        window.history.replaceState({}, "", "/goals")
        document.dispatchEvent(new Event("htmx:afterSettle"))
      })
      expect(path()).toBe("/goals")
    })
  })

  describe("shell mode (inside a router)", () => {
    test("updates from router navigation", async () => {
      const { router } = await renderInRouter(createElement(Probe), "/")
      expect(path()).toBe("/")

      await act(async () => {
        await router.navigate({ to: "/notifications" })
      })
      expect(path()).toBe("/notifications")
    })

    test("never registers an htmx:afterSettle listener", async () => {
      const addSpy = vi.spyOn(document, "addEventListener")
      try {
        await renderInRouter(createElement(Probe), "/")
        const registeredHtmx = addSpy.mock.calls.some(([type]) => type === "htmx:afterSettle")
        expect(registeredHtmx).toBe(false)
      } finally {
        addSpy.mockRestore()
      }
    })
  })
})
