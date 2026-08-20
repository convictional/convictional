import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { CollectionListRow } from "~/react/composites/meetings/CollectionListRow"

afterEach(cleanup)

describe("CollectionListRow", () => {
  test("links to the href and renders the icon and title", () => {
    render(<CollectionListRow href="/meetings_collections/c1" icon="folder" title="Weekly Sync" count={2} />)

    const link = screen.getByRole("link", { name: /Weekly Sync/ })
    expect(link).toHaveAttribute("href", "/meetings_collections/c1")
    expect(screen.getByText("folder")).toBeInTheDocument()
    expect(screen.getByText("Weekly Sync")).toBeInTheDocument()
  })

  test("renders the count badge when count is greater than zero", () => {
    render(<CollectionListRow href="/c" icon="folder" title="Sales" count={5} />)
    expect(screen.getByText("5")).toBeInTheDocument()
  })

  test("omits the count badge when count is zero or undefined", () => {
    const { rerender } = render(<CollectionListRow href="/c" icon="folder" title="Sales" count={0} />)
    expect(screen.queryByText("0")).not.toBeInTheDocument()

    rerender(<CollectionListRow href="/c" icon="folder" title="Sales" />)
    // No numeric badge rendered for an undefined count.
    expect(screen.queryByText(/^\d+$/)).not.toBeInTheDocument()
  })
})
