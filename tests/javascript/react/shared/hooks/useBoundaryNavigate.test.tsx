import { createRootRoute, createRoute, createRouter, Outlet, RouterProvider } from "@tanstack/react-router"
import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { useBoundaryNavigate } from "~/react/shared/hooks/useBoundaryNavigate"

const boostedNavigate = vi.fn()
vi.mock("~/react/shared/boostedNavigate", () => ({ boostedNavigate: (url: string) => boostedNavigate(url) }))

afterEach(() => {
  cleanup()
  boostedNavigate.mockClear()
})

// A button that navigates to `href` via the hook, so a click exercises the same
// path the mailbox arrows take.
function NavButton({ href }: { href: string }) {
  const navigate = useBoundaryNavigate()
  return (
    <button type="button" onClick={() => navigate(href)}>
      go
    </button>
  )
}

function click() {
  act(() => {
    screen.getByRole("button", { name: "go" }).click()
  })
}

// Minimal SPA shell: a static route and a parameterized one, mirroring the real
// tree. `/posts/$id` is intentionally absent — it stands in for a path still
// served by Jinja. Default browser history keeps window.location in sync.
async function renderInRouter(href: string, initialPath = "/") {
  window.history.replaceState({}, "", initialPath)
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: () => <NavButton href={href} /> })
  const notificationsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/notifications",
    component: () => null,
  })
  const chatShowRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/chats/$chatId",
    validateSearch: (search: Record<string, unknown>) => ({
      return_to: typeof search.return_to === "string" ? search.return_to : undefined,
      mailbox_entry_id: typeof search.mailbox_entry_id === "string" ? search.mailbox_entry_id : undefined,
    }),
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, notificationsRoute, chatShowRoute]),
  })
  const result = render(<RouterProvider router={router} />)
  await act(async () => {
    await router.load()
  })
  return { router, ...result }
}

describe("useBoundaryNavigate", () => {
  test("island mode (no router): falls back to boostedNavigate", () => {
    render(<NavButton href="/chats/abc?return_to=%2F" />)
    click()
    expect(boostedNavigate).toHaveBeenCalledWith("/chats/abc?return_to=%2F")
  })

  test("shell mode, registered static route: client-navigates without boostedNavigate", async () => {
    const { router } = await renderInRouter("/notifications")
    click()
    expect(router.latestLocation.pathname).toBe("/notifications")
    expect(boostedNavigate).not.toHaveBeenCalled()
  })

  test("shell mode, registered parameterized route: client-navigates and preserves query", async () => {
    const { router } = await renderInRouter("/chats/abc?mailbox_entry_id=e1&return_to=%2F")
    click()
    expect(router.latestLocation.pathname).toBe("/chats/abc")
    // mailbox_entry_id must survive the client hop — it gates the mailbox bar.
    expect(router.latestLocation.search).toMatchObject({ mailbox_entry_id: "e1", return_to: "/" })
    expect(boostedNavigate).not.toHaveBeenCalled()
  })

  test("shell mode, unregistered path: falls back to boostedNavigate (full-document load)", async () => {
    const { router } = await renderInRouter("/posts/2?return_to=%2F")
    click()
    expect(boostedNavigate).toHaveBeenCalledWith("/posts/2?return_to=%2F")
    expect(router.latestLocation.pathname).toBe("/")
  })
})
