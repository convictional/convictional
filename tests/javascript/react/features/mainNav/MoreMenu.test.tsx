import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { MoreMenu } from "../../../../../app/javascript/react/features/mainNav/MoreMenu"

vi.mock("@github/hotkey", () => ({
  install: vi.fn(),
  uninstall: vi.fn(),
}))

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

describe("MoreMenu", () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(cleanup)

  function open() {
    fireEvent.click(screen.getByRole("button", { name: /more options/i }))
  }

  test("non-admin user only sees public sections", () => {
    render(<MoreMenu {...baseProps} />)
    open()

    expect(screen.queryByRole("link", { name: "Organization Settings" })).toBeNull()
    expect(screen.queryByRole("link", { name: "Team Members" })).toBeNull()
    expect(screen.queryByRole("link", { name: "Background jobs" })).toBeNull()

    expect(screen.getByRole("link", { name: "Groups" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Guides" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Scheduled research/ })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Settings/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument()
  })

  test("admin user sees admin section including Groups", () => {
    render(<MoreMenu {...baseProps} isAdmin={true} />)
    open()

    expect(screen.getByRole("link", { name: "Organization Settings" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Team Members" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Groups" })).toBeInTheDocument()
  })

  test("superuser sees superuser section", () => {
    render(<MoreMenu {...baseProps} isSuperuser={true} />)
    open()
    expect(screen.getByRole("link", { name: "Background jobs" })).toBeInTheDocument()
  })

  test("logout form posts to /logout with the CSRF token from <meta>", () => {
    render(<MoreMenu {...baseProps} />)
    open()
    const logoutButton = screen.getByRole("button", { name: /logout/i })
    const form = logoutButton.closest("form")
    expect(form).toHaveAttribute("action", "/logout")
    expect(form).toHaveAttribute("method", "post")
    const tokenInput = form?.querySelector('input[name="csrf_token"]') as HTMLInputElement | null
    expect(tokenInput?.value).toBe("stub-csrf-token")
  })

  test("clicking Dark sets data-theme and persists to localStorage", () => {
    render(<MoreMenu {...baseProps} />)
    open()

    fireEvent.click(screen.getByRole("button", { name: "Dark" }))

    expect(document.documentElement.dataset.theme).toBe("convictional-dark")
    expect(localStorage.getItem("themeSetting")).toBe("dark")
  })
})
