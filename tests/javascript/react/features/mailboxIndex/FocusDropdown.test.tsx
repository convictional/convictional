import { cleanup, fireEvent, screen, waitFor } from "../../shared/testUtils"
import { renderWithMailboxRouterContext as render } from "./harness"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type {
  ActiveMailboxView,
  MailboxViewSummary,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback),
}))

vi.mock("../../../../../app/javascript/react/composites/confirmationDialog/confirm", () => ({
  confirm: vi.fn(async () => true),
}))

vi.mock("../../../../../app/javascript/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { FocusDropdown } from "../../../../../app/javascript/react/features/mailboxIndex/components/FocusDropdown"
import { resetCurrentUser } from "../../shared/currentUserFixtures"
import { showFlash } from "../../../../../app/javascript/shared/flash"

const mockApiFetch = vi.mocked(apiFetch)
const mockShowFlash = vi.mocked(showFlash)

function makeView(overrides: Partial<MailboxViewSummary> = {}): MailboxViewSummary {
  return {
    id: "v1",
    title: "Needs reply",
    view_request: "Group emails that need a reply",
    layout: "grouped",
    created_at: "2026-06-01T00:00:00Z",
    ...overrides,
  }
}

function renderDropdown(
  props: {
    allViews?: MailboxViewSummary[]
    active?: ActiveMailboxView | null
    hasGoalsForView?: boolean
    createView?: ReturnType<typeof vi.fn>
    updateView?: ReturnType<typeof vi.fn>
    deleteView?: ReturnType<typeof vi.fn>
  } = {}
) {
  const createView = props.createView ?? vi.fn(async () => {})
  const updateView = props.updateView ?? vi.fn(async () => {})
  const deleteView = props.deleteView ?? vi.fn(async () => {})
  const { router } = render(
    <FocusDropdown
      allViews={props.allViews ?? []}
      active={props.active ?? null}
      hasGoalsForView={props.hasGoalsForView ?? true}
      createView={createView}
      updateView={updateView}
      deleteView={deleteView}
    />
  )
  return { router, createView, updateView, deleteView }
}

function openDropdown() {
  // The repo uses `data-test-id` (not testing-library's default `data-testid`); open via role.
  fireEvent.click(screen.getByRole("button", { name: /Focus/ }))
}

beforeEach(() => {
  mockApiFetch.mockReset()
  mockShowFlash.mockReset()
  // The currentUser cache is a module singleton; clear it so each test re-fetches /api/users/me.
  resetCurrentUser()
  mockApiFetch.mockResolvedValue({ goals: [], next_cursor: null, has_more: false })
})

afterEach(cleanup)

describe("FocusDropdown", () => {
  test("splits saved views and sorts by layout, alongside built-in templates", async () => {
    renderDropdown({
      allViews: [
        makeView({ id: "v1", title: "Needs reply", layout: "grouped" }),
        makeView({ id: "s1", title: "Most urgent", layout: "ranked", view_request: "Rank by urgency" }),
      ],
    })
    openDropdown()

    expect(await screen.findByText("Custom Views")).toBeInTheDocument()
    expect(screen.getByText("Custom Sorts")).toBeInTheDocument()

    // Built-in templates render in their respective sections...
    expect(screen.getByText("Urgent/Important")).toBeInTheDocument()
    expect(screen.getByText("By Goals")).toBeInTheDocument()
    expect(screen.getByText("Priority")).toBeInTheDocument()
    // ...and the standing By goal sort.
    expect(screen.getByText("By goal")).toBeInTheDocument()

    // Saved view (grouped) links to its id; saved sort (ranked) likewise.
    expect(screen.getByRole("link", { name: /Needs reply/ })).toHaveAttribute("href", "/?mailbox_view_id=v1")
    expect(screen.getByRole("link", { name: /Most urgent/ })).toHaveAttribute("href", "/?mailbox_view_id=s1")
    // Built-in template links go through the template route.
    expect(screen.getByRole("link", { name: /Urgent\/Important/ })).toHaveAttribute(
      "href",
      "/?mailbox_view_template=urgent_important"
    )
    expect(screen.getByRole("link", { name: /Priority/ })).toHaveAttribute("href", "/?mailbox_view_template=priority")
  })

  test("hides the goals-gated entries when the user has no goals", async () => {
    renderDropdown({ hasGoalsForView: false })
    openDropdown()
    await screen.findByText("Custom Views")
    expect(screen.queryByText("By Goals")).toBeNull()
    expect(screen.queryByText("By goal")).toBeNull()
  })

  test("New view and New sort open the form in the matching kind", async () => {
    renderDropdown()
    openDropdown()
    fireEvent.click(await screen.findByText("New sort"))
    expect(await screen.findByText("New custom sort")).toBeInTheDocument()

    cleanup()
    renderDropdown()
    openDropdown()
    fireEvent.click(await screen.findByText("New view"))
    expect(await screen.findByText("New custom view")).toBeInTheDocument()
  })

  test("editing a saved sort opens the form prefilled in sort kind", async () => {
    renderDropdown({
      allViews: [makeView({ id: "s1", title: "Most urgent", layout: "ranked", view_request: "Rank by urgency" })],
    })
    openDropdown()
    fireEvent.click(await screen.findByLabelText("Edit sort"))
    expect(await screen.findByText("Edit custom sort")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Rank by urgency")).toBeInTheDocument()
  })

  test("picking a goal navigates (debounced) to the by_goal sort with that goal_id", async () => {
    mockApiFetch.mockResolvedValue({
      goals: [
        { id: "g1", title: "Ship the mobile app" },
        { id: "g2", title: "Cut p95 latency" },
      ],
      next_cursor: null,
      has_more: false,
    })
    const { router } = renderDropdown()
    openDropdown()
    fireEvent.click(await screen.findByLabelText("Change goal"))

    // Goals are lazy-loaded from /api/goals and surfaced in the picker.
    fireEvent.click(await screen.findByText("Ship the mobile app"))

    await waitFor(() => expect(router.state.location.href).toBe("/?mailbox_view_template=by_goal&goal_id=g1"))
    expect(mockApiFetch).toHaveBeenCalledWith("/api/goals", { signal: expect.any(AbortSignal) })
  })

  test("loads every page of /api/goals so the picker covers goals past the first page", async () => {
    // The picker filters client-side, so FocusDropdown must follow the cursor until has_more is
    // false — otherwise goals beyond the first page are invisible to search.
    mockApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/goals") {
        return { goals: [{ id: "g1", title: "Ship the mobile app" }], next_cursor: "c1", has_more: true }
      }
      if (path === "/api/goals?cursor=c1") {
        return { goals: [{ id: "g2", title: "Cut p95 latency" }], next_cursor: null, has_more: false }
      }
      return { groups: [], next_cursor: null, has_more: false }
    })

    renderDropdown()
    openDropdown()
    fireEvent.click(await screen.findByLabelText("Change goal"))

    // Both pages are surfaced in the picker.
    expect(await screen.findByText("Ship the mobile app")).toBeInTheDocument()
    expect(screen.getByText("Cut p95 latency")).toBeInTheDocument()
    expect(mockApiFetch).toHaveBeenCalledWith("/api/goals", { signal: expect.any(AbortSignal) })
    expect(mockApiFetch).toHaveBeenCalledWith("/api/goals?cursor=c1", { signal: expect.any(AbortSignal) })
  })

  test("a failed goals fetch flashes and retries instead of bricking the picker", async () => {
    // First /api/goals rejects; the picker must not latch to an empty list. Because goals stays
    // null (not []), a later ensureGoals call on the same instance retries and recovers.
    let goalsCalls = 0
    mockApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/goals") {
        goalsCalls += 1
        if (goalsCalls === 1) throw new Error("network")
        return { goals: [{ id: "g1", title: "Ship the mobile app" }], next_cursor: null, has_more: false }
      }
      return { groups: [], next_cursor: null, has_more: false }
    })

    renderDropdown()
    // Opening the dropdown triggers the first (failing) fetch — surfaced via flash, goals left null.
    openDropdown()
    await waitFor(() => expect(mockShowFlash).toHaveBeenCalled())

    // Opening the picker retries the fetch, which now succeeds and renders the goal.
    fireEvent.click(await screen.findByLabelText("Change goal"))
    expect(await screen.findByText("Ship the mobile app")).toBeInTheDocument()
    expect(goalsCalls).toBe(2)
  })

  test("renders a clear-focus control only when a focus is active", async () => {
    const { rerender } = render(
      <FocusDropdown
        allViews={[]}
        active={null}
        hasGoalsForView
        createView={vi.fn()}
        updateView={vi.fn()}
        deleteView={vi.fn()}
      />
    )
    expect(screen.queryByLabelText("Clear focus")).toBeNull()

    const active: ActiveMailboxView = {
      kind: "template",
      id: "template:priority",
      title: "Priority",
      view_request: null,
      channel_id: "template:priority",
      requires_goals: false,
      layout: "ranked",
    }
    rerender(
      <FocusDropdown
        allViews={[]}
        active={active}
        hasGoalsForView
        createView={vi.fn()}
        updateView={vi.fn()}
        deleteView={vi.fn()}
      />
    )
    // Clears to the default inbox via the sort path — a bare "/" would re-apply the persisted
    // focus cookie and bounce the user back to the active focus.
    expect(screen.getByLabelText("Clear focus")).toHaveAttribute("href", "/?sort=newest")
  })
})

describe("FocusDropdown (mobile)", () => {
  // `useIsMobile` reads `data-is-mobile` off <html> (set server-side by the layout). Flip it on
  // so the component takes its mobile branch: BottomSheet containers instead of Dropdown/Dialog.
  beforeEach(() => {
    document.documentElement.dataset.isMobile = "true"
  })

  afterEach(() => {
    delete document.documentElement.dataset.isMobile
  })

  test("opens the focus menu in a bottom sheet rather than a floating dropdown", async () => {
    renderDropdown({ allViews: [makeView({ id: "v1", title: "Needs reply", layout: "grouped" })] })
    openDropdown()

    // BottomSheet renders as an aria-labelled dialog; the menu body is the same as desktop.
    const sheet = await screen.findByRole("dialog", { name: "Focus views and sorts" })
    expect(sheet).toBeInTheDocument()
    expect(screen.getByText("Custom Views")).toBeInTheDocument()
    expect(screen.getByText("Custom Sorts")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Needs reply/ })).toHaveAttribute("href", "/?mailbox_view_id=v1")
  })

  test("New view opens the create form inside a bottom sheet", async () => {
    renderDropdown()
    openDropdown()
    fireEvent.click(await screen.findByText("New view"))

    expect(await screen.findByRole("dialog", { name: "Custom view" })).toBeInTheDocument()
    expect(screen.getByText("New custom view")).toBeInTheDocument()
  })

  test("Change goal opens the goal picker inside a bottom sheet", async () => {
    mockApiFetch.mockResolvedValue({
      goals: [{ id: "g1", title: "Ship the mobile app" }],
      next_cursor: null,
      has_more: false,
    })
    renderDropdown()
    openDropdown()
    fireEvent.click(await screen.findByLabelText("Change goal"))

    expect(await screen.findByRole("dialog", { name: "Sort by goal" })).toBeInTheDocument()
    expect(await screen.findByText("Ship the mobile app")).toBeInTheDocument()
  })

  test("edit/delete affordances are visible without hover on touch", async () => {
    renderDropdown({ allViews: [makeView({ id: "v1", title: "Needs reply", layout: "grouped" })] })
    openDropdown()

    // The action cluster is always shown on mobile (opacity-100) and only hover-revealed on
    // desktop (@desktop:opacity-0 + @desktop:group-hover) — no hover exists on touch.
    const editCluster = (await screen.findByLabelText("Edit view")).closest("span")
    expect(editCluster?.className).toContain("opacity-100")
    expect(editCluster?.className).toContain("@desktop:opacity-0")
    expect(editCluster?.className).toContain("@desktop:group-hover/entry:opacity-100")
  })
})
