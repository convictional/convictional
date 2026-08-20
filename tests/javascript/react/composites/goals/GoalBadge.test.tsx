import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { GoalBadge } from "~/react/composites/goals/GoalBadge"

afterEach(cleanup)

// Mounts the badge inside a router whose tree registers /goals/$goalId, so the
// typed-<Link> branch is exercised. Islands (mailbox, ProfileCard) render the badge
// with no RouterProvider at all, which every other case here covers.
async function renderInRouter(goalId: string) {
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const badgeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => <GoalBadge goal={{ id: goalId, title: "Ship Q2", description: "Ship the Q2 release" }} />,
  })
  const goalShowRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/goals/$goalId",
    component: () => <div data-testid="show-page" />,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([badgeRoute, goalShowRoute]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  const utils = render(<RouterProvider router={router} />)
  await act(async () => {
    await router.load()
  })
  return { router, ...utils }
}

describe("GoalBadge", () => {
  test("client-routes to the goal inside the SPA shell", async () => {
    const { router } = await renderInRouter("g1")

    const link = screen.getByRole("link", { name: "Ship Q2" })
    expect(link).toHaveAttribute("href", "/goals/g1")
    // The island branch opts out of hx-boost; the client-routed branch has no htmx.
    expect(link).not.toHaveAttribute("hx-boost")

    await act(async () => {
      link.click()
    })

    expect(router.state.location.pathname).toBe("/goals/g1")
    expect(screen.getByTestId("show-page")).toBeInTheDocument()
  })

  test("renders a link with title (falling back to description) and highlight/medium classes", () => {
    render(<GoalBadge goal={{ id: "g1", title: "Ship Q2", description: "Ship the Q2 release" }} />)

    const link = screen.getByRole("link", { name: "Ship Q2" })
    expect(link).toHaveAttribute("href", "/goals/g1")
    // In island mode htmx must not boost-fetch the SPA shell as a fragment.
    expect(link).toHaveAttribute("hx-boost", "false")
    expect(link).toHaveClass("bg-primary/10")
    expect(link.querySelector("div")).toHaveClass("px-3.5", "py-0.75")
    expect(link.querySelector("span")).toHaveClass("text-sm", "font-medium", "text-primary")
  })

  test("falls back to description when title is missing", () => {
    render(<GoalBadge goal={{ id: "g2", title: null, description: "Improve onboarding" }} />)

    expect(screen.getByRole("link", { name: "Improve onboarding" })).toBeInTheDocument()
  })

  test("renders parent breadcrumb when goal has a parent", () => {
    render(
      <GoalBadge
        goal={{
          id: "g3",
          title: "Subgoal title",
          description: "Subgoal description",
          parent: { description: "Parent description" },
        }}
      />
    )

    const link = screen.getByRole("link")
    expect(link).toHaveTextContent("Parent description")
    expect(link).toHaveTextContent("›")
    expect(link).toHaveTextContent("Subgoal description")
    // Subgoal branch shows description, not title
    expect(link).not.toHaveTextContent("Subgoal title")
  })

  test("applies beige theme and small size classes", () => {
    render(<GoalBadge goal={{ id: "g4", title: "Refactor pricing", description: "" }} theme="beige" size="small" />)

    const link = screen.getByRole("link", { name: "Refactor pricing" })
    expect(link).toHaveClass("bg-base-200", "border-neutral")
    expect(link).not.toHaveClass("bg-primary/10")
    expect(link.querySelector("div")).toHaveClass("px-2.5", "py-0.5")
    expect(link.querySelector("span")).toHaveClass("text-xs")
  })

  test("applies light theme classes", () => {
    render(<GoalBadge goal={{ id: "g5", title: "Launch", description: "" }} theme="light" />)

    expect(screen.getByRole("link")).toHaveClass("bg-base-50", "shadow-badge")
  })
})
