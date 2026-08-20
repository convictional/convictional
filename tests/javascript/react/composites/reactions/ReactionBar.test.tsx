import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { ReactionBar } from "~/react/composites/reactions/ReactionBar"

afterEach(cleanup)

const reactions = { thumbs_up: [{ id: "u1", display_name: "Bob" }] }

describe("ReactionBar", () => {
  test("clicking a reaction badge toggles it", () => {
    const onToggle = vi.fn()
    render(<ReactionBar reactions={reactions} currentUserId="viewer" onToggle={onToggle} />)
    fireEvent.click(screen.getByText("1").closest("button")!)
    expect(onToggle).toHaveBeenCalledWith("thumbs_up")
  })

  test("renders nothing when empty and hideWhenEmpty is set (chat's behavior)", () => {
    const { container } = render(
      <ReactionBar reactions={{ heart: [] }} currentUserId="viewer" onToggle={vi.fn()} hideWhenEmpty />
    )
    expect(container.firstChild).toBeNull()
  })

  test("keeps the add-reaction menu visible when empty without hideWhenEmpty (posts' behavior)", () => {
    const { container } = render(<ReactionBar reactions={{ heart: [] }} currentUserId="viewer" onToggle={vi.fn()} />)
    expect(container.firstChild).not.toBeNull()
    expect(screen.getByLabelText("Add reaction")).toBeTruthy()
  })
})
