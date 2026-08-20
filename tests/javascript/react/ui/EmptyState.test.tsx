import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { EmptyState } from "~/react/ui/EmptyState"

afterEach(cleanup)

describe("EmptyState", () => {
  test("renders title, text, and children with mb-4 on text", () => {
    const { container } = render(
      <EmptyState title="Inbox zero" text="You've cleared your inbox.">
        <a href="/goals">All goals</a>
      </EmptyState>
    )

    expect(screen.getByText("Inbox zero")).toBeInTheDocument()
    const text = screen.getByText("You've cleared your inbox.")
    expect(text).toHaveClass("mb-4")
    expect(screen.getByRole("link", { name: "All goals" })).toBeInTheDocument()
  })

  test("omits mb-4 from text when no children are provided", () => {
    render(<EmptyState title="Nothing here" text="Empty." />)

    expect(screen.getByText("Empty.")).not.toHaveClass("mb-4")
  })

  test("omits title and text when not provided", () => {
    const { container } = render(<EmptyState />)

    expect(container.querySelector("p")).toBeNull()
  })
})
