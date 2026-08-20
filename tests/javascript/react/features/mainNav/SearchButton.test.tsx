import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { SearchButton } from "../../../../../app/javascript/react/features/mainNav/SearchButton"

vi.mock("../../../../../app/javascript/react/ui/Tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

describe("SearchButton", () => {
  afterEach(cleanup)

  test("dispatches command-palette:toggle on click", () => {
    const spy = vi.fn()
    window.addEventListener("command-palette:toggle", spy)
    render(<SearchButton />)

    fireEvent.click(screen.getByRole("button", { name: "Search" }))

    expect(spy).toHaveBeenCalledTimes(1)
    window.removeEventListener("command-palette:toggle", spy)
  })

  test("mirrors opened / closed events as active styling", () => {
    render(<SearchButton />)
    const button = screen.getByRole("button", { name: "Search" })

    expect(button.className).not.toContain("bg-base-300")
    act(() => {
      window.dispatchEvent(new CustomEvent("command-palette:opened"))
    })
    expect(button.className).toContain("bg-base-300")
    act(() => {
      window.dispatchEvent(new CustomEvent("command-palette:closed"))
    })
    expect(button.className).not.toContain("bg-base-300")
  })
})
