import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { MobileBottomNav } from "../../../../../app/javascript/react/features/mainNav/MobileBottomNav"

vi.mock("../../../../../app/javascript/shared/csrf", () => ({
  getCSRFToken: () => "stub-csrf-token",
  isCSRFFailure: () => false,
  showSessionChangedFlash: () => {},
  initSessionBroadcast: () => {},
}))

const baseProps = {
  isAdmin: false,
  isSuperuser: false,
  organizationName: "Acme Inc.",
}

describe("MobileBottomNav", () => {
  afterEach(cleanup)

  test("renders the primary tabs and a More button", () => {
    render(<MobileBottomNav {...baseProps} />)

    expect(screen.getByText("Inbox")).toBeInTheDocument()
    expect(screen.getByText("Chat")).toBeInTheDocument()
    expect(screen.getByText("Posts")).toBeInTheDocument()
    expect(screen.queryByText("Docs")).toBeNull()
    expect(screen.getByRole("button", { name: /more/i })).toBeInTheDocument()
  })

  test("opens the More sheet revealing the secondary items", () => {
    render(<MobileBottomNav {...baseProps} />)

    const moreButton = screen.getByRole("button", { name: /more/i })
    expect(moreButton).toHaveAttribute("aria-expanded", "false")
    fireEvent.click(moreButton)

    expect(screen.getByText("Docs")).toBeInTheDocument()
    expect(screen.getByText("Goals")).toBeInTheDocument()
    expect(screen.getByText("Meetings")).toBeInTheDocument()
    expect(moreButton).toHaveAttribute("aria-expanded", "true")
  })

  test("More sheet shows admin section only for admins", () => {
    const { unmount } = render(<MobileBottomNav {...baseProps} />)
    fireEvent.click(screen.getByRole("button", { name: /more/i }))
    expect(screen.queryByText("Organization Settings")).toBeNull()
    unmount()

    render(<MobileBottomNav {...baseProps} isAdmin={true} />)
    fireEvent.click(screen.getByRole("button", { name: /more/i }))
    expect(screen.getByText("Organization Settings")).toBeInTheDocument()
    expect(screen.getByText("Team Members")).toBeInTheDocument()
  })

  test("More sheet shows superuser section only for superusers", () => {
    render(<MobileBottomNav {...baseProps} isSuperuser={true} />)
    fireEvent.click(screen.getByRole("button", { name: /more/i }))

    expect(screen.getByText("Background jobs")).toBeInTheDocument()
  })

  test("More sheet closes on Escape", () => {
    render(<MobileBottomNav {...baseProps} />)
    fireEvent.click(screen.getByRole("button", { name: /more/i }))
    expect(screen.getByText("Goals")).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Escape" })

    // Escape starts the close animation; the sheet unmounts when it ends.
    fireEvent.animationEnd(screen.getByRole("dialog"))

    expect(screen.queryByText("Goals")).not.toBeInTheDocument()
  })
})
