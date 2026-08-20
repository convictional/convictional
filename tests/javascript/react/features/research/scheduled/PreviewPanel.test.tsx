import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { PreviewPanel } from "~/react/features/research/scheduled/components/PreviewPanel"

afterEach(() => {
  cleanup()
})

describe("PreviewPanel", () => {
  test("renders nothing when idle and empty", () => {
    const { container } = render(<PreviewPanel status="idle" text="" errorMessage={null} />)
    // Collapsed to nothing when there's no content; the caller owns the trigger button.
    expect(container.firstChild).toBeNull()
  })

  test("shows a loading spinner when initiating before any delta arrives", () => {
    render(<PreviewPanel status="initiating" text="" errorMessage={null} />)
    expect(screen.getByText(/Generating…/i)).toBeInTheDocument()
  })

  test("renders markdown content once deltas accumulate", () => {
    const markdown = ["## Heading", "", "- item one"].join("\n")
    const { container } = render(<PreviewPanel status="streaming" text={markdown} errorMessage={null} />)

    expect(container.querySelector("h2")?.textContent).toBe("Heading")
    expect(container.querySelector("li")?.textContent).toContain("item one")
  })

  test("shows an error message when the stream errors", () => {
    render(<PreviewPanel status="error" text="" errorMessage="Something broke" />)

    expect(screen.getByTestId("scheduled-research-preview-error")).toHaveTextContent("Something broke")
  })
})
