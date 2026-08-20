import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
  errorMessage: (_err: unknown, fallback: string) => fallback,
}))

import { apiFetch } from "~/react/shared/apiFetch"
import { WelcomeShow } from "~/react/features/mailboxIndex/components/WelcomeShow"

import { resetCurrentUser, setCurrentUser } from "../../shared/currentUserFixtures"
import { cleanup, screen, waitFor } from "../../shared/testUtils"
import { renderWithMailboxRouterContext as render } from "./harness"

const mockApiFetch = vi.mocked(apiFetch)
const noop = () => {}
const showProps = { read: false, onToggleRead: noop, onBack: noop, onArchive: noop, onSnooze: noop }

const ORG_SECTION = "Your organization's name, shown across the app."
const ORG_CLAUSE = /you can set the organization name/

beforeEach(() => {
  mockApiFetch.mockReset()
  // The mount fetches the profile; resolve it so the show leaves its loading state.
  mockApiFetch.mockResolvedValue({ name: "Viewer", picture: null, has_custom_avatar: false })
})

afterEach(() => {
  cleanup()
  resetCurrentUser()
})

describe("WelcomeShow", () => {
  test("offers organization naming only to an admin whose org is unnamed", async () => {
    // Admin, org not yet named: the naming section, the subheading clause, and the
    // Organization Settings link all appear.
    setCurrentUser({ id: "u1", is_admin: true, organization_name: null })
    render(<WelcomeShow {...showProps} />)
    await waitFor(() => expect(screen.getByText("Your profile")).toBeTruthy())
    expect(screen.getByText(ORG_SECTION)).toBeTruthy()
    expect(screen.getByText(ORG_CLAUSE)).toBeTruthy()
    expect(screen.getByRole("link", { name: "Organization Settings" })).toBeTruthy()
    cleanup()
    resetCurrentUser()

    // Non-admin: no naming section, no clause, no org link.
    setCurrentUser({ id: "u2", is_admin: false, organization_name: null })
    render(<WelcomeShow {...showProps} />)
    await waitFor(() => expect(screen.getByText("Your profile")).toBeTruthy())
    expect(screen.queryByText(ORG_SECTION)).toBeNull()
    expect(screen.queryByText(ORG_CLAUSE)).toBeNull()
    expect(screen.queryByRole("link", { name: "Organization Settings" })).toBeNull()
    cleanup()
    resetCurrentUser()

    // Admin whose org is already named: nothing left to name, so no naming section,
    // but the Organization Settings link still shows (admins can always edit it).
    setCurrentUser({ id: "u3", is_admin: true, organization_name: "Acme" })
    render(<WelcomeShow {...showProps} />)
    await waitFor(() => expect(screen.getByText("Your profile")).toBeTruthy())
    expect(screen.queryByText(ORG_SECTION)).toBeNull()
    expect(screen.getByRole("link", { name: "Organization Settings" })).toBeTruthy()
  })
})
