import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

// Render the Dropdown's panel inline so the emoji picker is testable without
// driving floating-ui's open state.
vi.mock("~/react/ui/Dropdown", () => ({
  Dropdown: ({
    children,
  }: {
    children: ((args: { close: () => void }) => React.ReactNode) | React.ReactNode
  }) => <div>{typeof children === "function" ? children({ close: vi.fn() }) : children}</div>,
}))

vi.mock("~/react/ui/Tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

import { Reactions } from "~/react/composites/reactions/Reactions"

afterEach(cleanup)

describe("Reactions", () => {
  it("renders a chip per non-empty reaction and toggles on click", () => {
    const onToggle = vi.fn()
    const reactions = {
      thumbs_up: [
        { id: "viewer", display_name: "Me" },
        { id: "u2", display_name: "Bob" },
      ],
      heart: [],
    }
    render(<Reactions reactions={reactions} currentUserId="viewer" onToggle={onToggle} />)

    // Empty buckets render no chip; only the thumbs_up chip shows its count.
    const chip = screen.getByText("2").closest("button")!
    fireEvent.click(chip)
    expect(onToggle).toHaveBeenCalledWith("thumbs_up")
  })

  it("exposes the full emoji picker and toggles the picked reaction", () => {
    const onToggle = vi.fn()
    render(<Reactions reactions={{}} currentUserId={null} onToggle={onToggle} />)

    const partyButton = screen.getByLabelText("party popper").closest("button")!
    fireEvent.click(partyButton)
    expect(onToggle).toHaveBeenCalledWith("party_popper")
  })
})
