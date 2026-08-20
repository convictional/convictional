import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { InboxSetupBanner } from "~/react/features/mailboxIndex/components/InboxSetupBanner"
import type { InboxProgressResponse } from "~/react/features/mailboxIndex/types"

function makeState(overrides: Partial<InboxProgressResponse> = {}): InboxProgressResponse {
  return {
    is_onboarding_mailbox_sync_complete: true,
    onboarding_mailbox_sync_started_at: null,
    has_gmail_integration: false,
    has_calendar_integration: false,
    is_google_authenticated: true,
    ...overrides,
  }
}

// The Gmail dismissal persists in localStorage, so clear it between tests to keep
// a dismissal from suppressing the banner in later ones.
beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("InboxSetupBanner", () => {
  test("gates the Gmail-not-connected prompt on the user being Google-authenticated", () => {
    // Microsoft (non-Google) user who finished onboarding without Gmail: there's
    // no Gmail to connect, so the prompt must not surface.
    const { rerender } = render(
      <InboxSetupBanner
        state={makeState({ is_google_authenticated: false })}
        gmailAuthUrl="https://auth.example/gmail"
      />
    )
    expect(screen.queryByText("Gmail not connected")).toBeNull()
    expect(screen.queryByText("Connect Gmail")).toBeNull()

    // Same onboarding state for a Google user: the prompt renders and the
    // Connect action points at the supplied Gmail auth URL.
    rerender(
      <InboxSetupBanner
        state={makeState({ is_google_authenticated: true })}
        gmailAuthUrl="https://auth.example/gmail"
      />
    )
    expect(screen.getByText("Gmail not connected")).toBeTruthy()
    const connectLink = screen.getByRole("link", { name: /Connect Gmail/ })
    expect(connectLink).toHaveAttribute("href", "https://auth.example/gmail")
  })

  test("still shows the syncing banner while an in-progress sync runs", () => {
    render(
      <InboxSetupBanner
        state={makeState({
          onboarding_mailbox_sync_started_at: "2026-06-01T00:00:00Z",
          is_onboarding_mailbox_sync_complete: false,
        })}
      />
    )
    expect(screen.getByText("Syncing your Gmail")).toBeTruthy()
  })

  test("honours a dismissal of the Gmail prompt for an hour across remounts", () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-06-01T12:00:00Z"))

    const gmailBanner = () => <InboxSetupBanner state={makeState()} gmailAuthUrl="https://auth.example/gmail" />
    render(gmailBanner())
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }))
    expect(screen.queryByText("Gmail not connected")).toBeNull()

    // A remount stands in for a page load: the dismissal outlives component state.
    cleanup()
    vi.setSystemTime(new Date("2026-06-01T12:59:59Z"))
    render(gmailBanner())
    expect(screen.queryByText("Gmail not connected")).toBeNull()

    cleanup()
    vi.setSystemTime(new Date("2026-06-01T13:00:00Z"))
    render(gmailBanner())
    expect(screen.getByText("Gmail not connected")).toBeTruthy()
  })

  test("shows the Gmail prompt when the stored dismissal is unreadable", () => {
    window.localStorage.setItem("inbox-gmail-banner-dismissed-at", "never")

    render(<InboxSetupBanner state={makeState()} gmailAuthUrl="https://auth.example/gmail" />)
    expect(screen.getByText("Gmail not connected")).toBeTruthy()
  })

  test("keeps the syncing banner dismissal in-memory only", () => {
    const syncingBanner = () => (
      <InboxSetupBanner
        state={makeState({
          onboarding_mailbox_sync_started_at: "2026-06-01T00:00:00Z",
          is_onboarding_mailbox_sync_complete: false,
        })}
      />
    )
    render(syncingBanner())
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }))
    expect(screen.queryByText("Syncing your Gmail")).toBeNull()

    // Sync progress is transient, so a reload should surface it again.
    cleanup()
    render(syncingBanner())
    expect(screen.getByText("Syncing your Gmail")).toBeTruthy()
  })
})
