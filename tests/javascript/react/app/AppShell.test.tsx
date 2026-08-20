import * as Sentry from "@sentry/browser"
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { FLOATING_PORTAL_ROOT_ID } from "~/react/ui/floatingPortalRoot"

vi.mock("@sentry/browser", () => ({ setUser: vi.fn() }))

const state = vi.hoisted(() => ({
  user: null as Record<string, unknown> | null,
  isMobile: false,
  flashes: [] as { content: string; level: string }[],
}))

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }))

// Stub the chrome children to sentinels — this test asserts the shell composes
// them, not their internals (covered by their own suites). Channel boot and the
// toast bridge live in the route's beforeLoad now, covered by shellBootstrap.test.
function sentinel(testid: string) {
  return () => <div data-testid={testid} />
}

vi.mock("@tanstack/react-router", () => ({
  Outlet: () => <div data-testid="outlet" />,
  useMatches: () => [],
}))
vi.mock("~/react/features/mainNav/MainNav", () => ({ MainNav: sentinel("main-nav") }))
vi.mock("~/react/features/commandPalette/CommandPalette", () => ({ CommandPalette: sentinel("command-palette") }))
vi.mock("~/react/features/research/dialog/ResearchDialog", () => ({ ResearchDialog: sentinel("research-dialog") }))
vi.mock("~/react/features/feedback/FeedbackDialog", () => ({ FeedbackDialog: sentinel("feedback-dialog") }))
vi.mock("~/react/features/chatPanel/ChatPanel", () => ({ ChatPanel: sentinel("chat-panel") }))
vi.mock("~/react/composites/confirmationDialog/ConfirmationDialog", () => ({
  ConfirmationDialog: sentinel("confirmation-dialog"),
}))
vi.mock("~/react/composites/toaster/Toaster", () => ({ Toaster: sentinel("toaster") }))

vi.mock("~/react/shared/hooks/useIsMobile", () => ({ useIsMobile: () => state.isMobile }))
vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ user: state.user, clientConfig: null, loading: false, error: null }),
}))
vi.mock("~/react/shared/stores/currentUser", () => ({
  consumeFlashes: () => {
    const drained = state.flashes
    state.flashes = []
    return drained
  },
}))
vi.mock("~/react/shared/stores/toast", () => ({
  toastStore: { getState: () => ({ show: showToast }) },
}))

import { AppShell } from "~/react/app/AppShell"

const user = {
  id: "u1",
  email: "ada@example.com",
  is_admin: true,
  is_superuser: false,
  organization_id: "org-1",
  organization_name: "Acme",
  time_zone: "UTC",
  feedback_upload_url: "/upload",
}

describe("AppShell", () => {
  beforeEach(() => {
    state.user = { ...user }
    state.isMobile = false
    state.flashes = []
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  test("renders the nav, all chrome, the portal root, and the outlet", () => {
    const { container } = render(<AppShell />)

    for (const id of [
      "main-nav",
      "command-palette",
      "research-dialog",
      "feedback-dialog",
      "confirmation-dialog",
      "toaster",
      "chat-panel",
      "outlet",
    ]) {
      expect(screen.getByTestId(id)).toBeInTheDocument()
    }
    expect(container.querySelector(`#${FLOATING_PORTAL_ROOT_ID}`)).not.toBeNull()
  })

  test("hides the desktop chat panel on mobile", () => {
    state.isMobile = true
    render(<AppShell />)

    expect(screen.queryByTestId("chat-panel")).toBeNull()
    // The rest of the chrome still renders on mobile.
    expect(screen.getByTestId("main-nav")).toBeInTheDocument()
  })

  test("sets the Sentry user on mount", () => {
    render(<AppShell />)

    expect(Sentry.setUser).toHaveBeenCalledWith({ id: "u1", email: "ada@example.com" })
  })

  test("clears the Sentry user when there is no user", () => {
    state.user = null
    render(<AppShell />)

    expect(Sentry.setUser).toHaveBeenCalledWith(null)
  })

  test("drains bootstrap server flashes into the toaster once", () => {
    state.flashes = [
      { content: "Saved", level: "success" },
      { content: "Heads up", level: "warning" },
    ]
    render(<AppShell />)

    expect(showToast).toHaveBeenCalledWith({ message: "Saved", level: "success", persistent: false })
    expect(showToast).toHaveBeenCalledWith({ message: "Heads up", level: "error", persistent: false })
  })
})
