import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test } from "vitest"

import { ChatImage } from "~/react/ui/ChatImage"

beforeEach(() => window.localStorage.clear())
afterEach(() => {
  cleanup()
  window.localStorage.clear()
})

describe("ChatImage", () => {
  test("renders an img with the given src and alt", () => {
    render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    const img = screen.getByAltText("a cat") as HTMLImageElement
    expect(img.tagName).toBe("IMG")
    expect(img.src).toBe("https://example.com/cat.png")
  })

  test("applies a height-cap class so single images can't dominate the chat", () => {
    const { container } = render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    const img = container.querySelector("img")
    expect(img?.className).toMatch(/\bmax-h-\[/)
  })

  test("does not render the lightbox until the image is clicked", () => {
    render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    // Before click: the only img in the document is the inline one (no modal copy).
    expect(screen.getAllByAltText("a cat")).toHaveLength(1)
    expect(screen.queryByLabelText("Close")).not.toBeInTheDocument()
  })

  test("clicking the image opens a lightbox with the image and a close button", () => {
    render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    fireEvent.click(screen.getByAltText("a cat"))

    // Lightbox is open: a second copy of the image is in the modal, plus the controls.
    expect(screen.getAllByAltText("a cat").length).toBeGreaterThan(1)
    expect(screen.getByLabelText("Close")).toBeInTheDocument()
  })

  test("clicking the close button dismisses the lightbox", () => {
    render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    fireEvent.click(screen.getByAltText("a cat"))
    expect(screen.getByLabelText("Close")).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText("Close"))
    expect(screen.queryByLabelText("Close")).not.toBeInTheDocument()
    // The inline image is still there afterwards.
    expect(screen.getAllByAltText("a cat")).toHaveLength(1)
  })

  test("pressing Escape dismisses the lightbox", () => {
    render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    fireEvent.click(screen.getByAltText("a cat"))
    expect(screen.getByLabelText("Close")).toBeInTheDocument()

    fireEvent.keyDown(document.body, { key: "Escape" })
    expect(screen.queryByLabelText("Close")).not.toBeInTheDocument()
  })

  test("lightbox offers a download link pointing at the image", () => {
    render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    fireEvent.click(screen.getByAltText("a cat"))

    const download = screen.getByLabelText("Download") as HTMLAnchorElement
    expect(download.tagName).toBe("A")
    expect(download.href).toBe("https://example.com/cat.png")
    expect(download.hasAttribute("download")).toBe(true)
  })

  test("clicking the letterbox area around the image closes the lightbox; clicking the image does not", () => {
    render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    fireEvent.click(screen.getByAltText("a cat"))

    // The image container inside the lightbox dialog is the click-to-dismiss target.
    const dialog = screen.getByRole("dialog")
    const container = dialog.querySelector("div") as HTMLElement
    const modalImg = container.querySelector("img") as HTMLElement

    // Clicking the image itself keeps the lightbox open.
    fireEvent.click(modalImg)
    expect(screen.getByLabelText("Close")).toBeInTheDocument()

    // Clicking the container (the dark letterbox) dismisses.
    fireEvent.click(container)
    expect(screen.queryByLabelText("Close")).not.toBeInTheDocument()
  })

  test("collapsing replaces the image with a chip and expanding restores it; the choice persists", () => {
    const { unmount } = render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    fireEvent.click(screen.getByLabelText("Hide image"))

    // Image is gone; a 'Show' chip is in its place.
    expect(screen.queryByAltText("a cat")).not.toBeInTheDocument()
    const chip = screen.getByText("Show", { exact: false })
    expect(chip).toBeInTheDocument()

    // A fresh mount stays collapsed (persisted).
    unmount()
    render(<ChatImage src="https://example.com/cat.png" alt="a cat" />)
    expect(screen.queryByAltText("a cat")).not.toBeInTheDocument()

    // Expanding brings the image back.
    fireEvent.click(screen.getByText("Show", { exact: false }))
    expect(screen.getByAltText("a cat")).toBeInTheDocument()
  })
})
