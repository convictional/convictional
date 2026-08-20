import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { BackButton } from "~/react/composites/BackButton"

const BACK = { url: "/inbox?filter=all", label: "Back to inbox" }

afterEach(cleanup)

describe("BackButton", () => {
  test("renders a labeled link with the back url and an accessible name", () => {
    render(<BackButton back={BACK} />)

    const link = screen.getByRole("link", { name: "Back to inbox" })
    expect(link).toHaveAttribute("href", "/inbox?filter=all")
    // Label is visible (responsive), not icon-only.
    expect(screen.getByText("Back to inbox")).toBeInTheDocument()
    expect(link).not.toHaveClass("btn-square")
  })

  test("iconOnly renders no visible label but keeps the accessible name", () => {
    render(<BackButton back={BACK} iconOnly />)

    const link = screen.getByRole("link", { name: "Back to inbox" })
    expect(link).toHaveClass("btn-square")
    expect(screen.queryByText("Back to inbox")).not.toBeInTheDocument()
  })

  test("appends extra classes without dropping the base btn class", () => {
    render(<BackButton back={BACK} className="border border-neutral" />)

    const link = screen.getByRole("link", { name: "Back to inbox" })
    expect(link).toHaveClass("btn", "border", "border-neutral")
  })

  test("installs the `u` hotkey that clicks the link", () => {
    render(<BackButton back={BACK} />)
    const clickSpy = vi.spyOn(screen.getByRole("link", { name: "Back to inbox" }), "click")

    fireEvent.keyDown(document.body, { key: "u" })

    expect(clickSpy).toHaveBeenCalledTimes(1)
  })

  test("does not install the hotkey when disabled", () => {
    render(<BackButton back={BACK} hotkeyEnabled={false} />)
    const clickSpy = vi.spyOn(screen.getByRole("link", { name: "Back to inbox" }), "click")

    fireEvent.keyDown(document.body, { key: "u" })

    expect(clickSpy).not.toHaveBeenCalled()
  })
})
