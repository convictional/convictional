import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

// MobileTopBar mounts useResearchProgress, which subscribes to a channel by the
// current user id; the subscription isn't under test here and would otherwise
// reach the channels client (absent in jsdom) and warn. Stub the channel hook
// and the current-user source.
vi.mock("~/react/shared/hooks/useChannel", () => ({ useChannel: vi.fn() }))
vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ user: { id: "user-1" }, clientConfig: null, loading: false, error: null }),
}))

import { MobileTopBar } from "../../../../../app/javascript/react/features/mainNav/MobileTopBar"

describe("MobileTopBar", () => {
  afterEach(cleanup)

  test("dispatches research-dialog:open on Research button click", () => {
    const spy = vi.fn()
    window.addEventListener("research-dialog:open", spy)
    render(<MobileTopBar />)

    fireEvent.click(screen.getByRole("button", { name: "Research" }))

    expect(spy).toHaveBeenCalledTimes(1)
    window.removeEventListener("research-dialog:open", spy)
  })

  test("dispatches mobile-search:open on Search button click", () => {
    const spy = vi.fn()
    window.addEventListener("mobile-search:open", spy)
    render(<MobileTopBar />)

    fireEvent.click(screen.getByRole("button", { name: "Search" }))

    expect(spy).toHaveBeenCalledTimes(1)
    window.removeEventListener("mobile-search:open", spy)
  })

  test("creates and focuses a temporary input for iOS keyboard claim on click", () => {
    render(<MobileTopBar />)

    const appendSpy = vi.spyOn(document.body, "appendChild")
    fireEvent.click(screen.getByRole("button", { name: "Research" }))

    const tempInput = appendSpy.mock.calls.find(
      ([el]) => el instanceof HTMLInputElement && el.style.opacity === "0"
    )
    expect(tempInput).toBeDefined()
    appendSpy.mockRestore()
  })

  test("highlights Research button when research dialog is open", () => {
    render(<MobileTopBar />)

    const researchButton = screen.getByRole("button", { name: "Research" })
    expect(researchButton.className).toContain("text-base-content/50")

    fireEvent(window, new CustomEvent("research-dialog:open"))
    expect(researchButton.className).toContain("text-primary")

    fireEvent(window, new CustomEvent("research-dialog:closed"))
    expect(researchButton.className).toContain("text-base-content/50")
  })
})
