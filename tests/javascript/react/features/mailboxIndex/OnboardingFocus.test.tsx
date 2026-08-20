import { afterEach, describe, expect, test } from "vitest"

import { OnboardingFocus } from "~/react/features/mailboxIndex/components/OnboardingFocus"

import { resetCurrentUser, setCurrentUser } from "../../shared/currentUserFixtures"
import { cleanup, render, screen } from "../../shared/testUtils"

const noop = () => {}

const baseProps = {
  gmailConnected: false,
  gmailAuthUrl: "https://auth.example/gmail",
  calendarConnected: false,
  calendarAuthUrl: "https://auth.example/calendar",
  welcomeSkipped: false,
  welcomeRead: false,
  onOpenWelcome: noop,
  onArchiveWelcome: noop,
  onSnoozeWelcome: noop,
  onToggleWelcomeRead: noop,
}

afterEach(() => {
  cleanup()
  resetCurrentUser()
  delete document.documentElement.dataset.isMobile
})

describe("OnboardingFocus", () => {
  test("shows every getting-started row and hides each on its own condition", () => {
    setCurrentUser({ id: "u1" })
    const { rerender } = render(<OnboardingFocus {...baseProps} />)
    expect(screen.getByText("Create your profile")).toBeTruthy()
    expect(screen.getByText("Connect your email")).toBeTruthy()
    expect(screen.getByText("Connect your calendar")).toBeTruthy()

    // welcomeSkipped drops the Welcome row.
    rerender(<OnboardingFocus {...baseProps} welcomeSkipped={true} />)
    expect(screen.queryByText("Create your profile")).toBeNull()

    // A connected integration drops its own setup row.
    rerender(<OnboardingFocus {...baseProps} gmailConnected={true} calendarConnected={true} />)
    expect(screen.queryByText("Connect your email")).toBeNull()
    expect(screen.queryByText("Connect your calendar")).toBeNull()

    // No auth URL → no Gmail row even while disconnected (nothing to link to).
    rerender(<OnboardingFocus {...baseProps} gmailAuthUrl={undefined} />)
    expect(screen.queryByText("Connect your email")).toBeNull()
  })

  test("names the organization in the Welcome row only for an admin whose org is unnamed", () => {
    // Non-admin: generic profile preview.
    setCurrentUser({ id: "u1", is_admin: false })
    render(<OnboardingFocus {...baseProps} />)
    expect(screen.getByText("Customize your name and photo")).toBeTruthy()
    cleanup()
    resetCurrentUser()

    // Admin whose org is already named: nothing left to name, so still generic.
    setCurrentUser({ id: "u1", is_admin: true, organization_name: "Acme" })
    render(<OnboardingFocus {...baseProps} />)
    expect(screen.getByText("Customize your name and photo")).toBeTruthy()
    cleanup()
    resetCurrentUser()

    // Admin with an unnamed org: the preview invites naming the organization.
    setCurrentUser({ id: "u1", is_admin: true, organization_name: null })
    render(<OnboardingFocus {...baseProps} />)
    expect(screen.getByText("Customize your name, photo, and organization")).toBeTruthy()
  })

  test("surfaces the connect actions inline on mobile (no hover needed)", () => {
    document.documentElement.dataset.isMobile = "true"
    setCurrentUser({ id: "u1" })
    render(<OnboardingFocus {...baseProps} />)

    // The Gmail card is a tappable connect link; the calendar Connect is an always-visible button.
    expect(screen.getByRole("link", { name: /Connect/ })).toHaveAttribute("href", "https://auth.example/gmail")
    expect(screen.getByRole("button", { name: /Connect calendar/ })).toBeTruthy()
    // The Welcome row still opens on tap.
    expect(screen.getByRole("button", { name: /Create your profile/ })).toBeTruthy()
  })
})
