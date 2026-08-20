import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test } from "vitest"

import { ChatImageGallery } from "~/react/ui/ChatImageGallery"

beforeEach(() => window.localStorage.clear())
afterEach(() => {
  cleanup()
  window.localStorage.clear()
})

function makeImages(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    src: `https://example.com/img-${i}.png`,
    alt: `image ${i}`,
  }))
}

describe("ChatImageGallery", () => {
  test("renders a single image as inline ChatImage (no grid tiles)", () => {
    const { container } = render(<ChatImageGallery images={makeImages(1)} />)
    expect(screen.getByAltText("image 0")).toBeInTheDocument()
    expect(container.querySelector(".grid")).toBeNull()
  })

  test("renders a 2x2 grid for 4 images", () => {
    const { container } = render(<ChatImageGallery images={makeImages(4)} />)
    for (let i = 0; i < 4; i++) {
      expect(screen.getByAltText(`image ${i}`)).toBeInTheDocument()
    }
    expect(container.querySelector(".grid-rows-2")).not.toBeNull()
    expect(container.querySelector(".row-span-2")).toBeNull()
  })

  test("renders two side-by-side tiles for 2 images (single-row grid)", () => {
    const { container } = render(<ChatImageGallery images={makeImages(2)} />)
    expect(screen.getByAltText("image 0")).toBeInTheDocument()
    expect(screen.getByAltText("image 1")).toBeInTheDocument()
    expect(container.querySelector(".grid-rows-1")).not.toBeNull()
    expect(container.querySelector(".grid-rows-2")).toBeNull()
  })

  test("renders three tiles for 3 images with a tall left tile (no +N overlay)", () => {
    const { container } = render(<ChatImageGallery images={makeImages(3)} />)
    for (let i = 0; i < 3; i++) {
      expect(screen.getByAltText(`image ${i}`)).toBeInTheDocument()
    }
    expect(screen.queryByText(/^\+\d+$/)).not.toBeInTheDocument()
    // The first tile spans both rows; the other two fill the right column.
    const spanning = container.querySelectorAll(".row-span-2")
    expect(spanning.length).toBe(1)
    expect(spanning[0].querySelector("img")?.getAttribute("alt")).toBe("image 0")
  })

  test("shows a +N overlay on the 4th tile when there are more than 4 images", () => {
    render(<ChatImageGallery images={makeImages(7)} />)
    expect(screen.getByText("+3")).toBeInTheDocument()
    // Tiles 0..3 are visible; 4..6 are not rendered as tiles.
    expect(screen.getByAltText("image 3")).toBeInTheDocument()
    expect(screen.queryByAltText("image 4")).not.toBeInTheDocument()
  })

  test("clicking a tile opens the lightbox at that image", () => {
    render(<ChatImageGallery images={makeImages(4)} />)
    fireEvent.click(screen.getByAltText("image 2"))

    // The lightbox renders a second copy of the clicked image, plus controls.
    expect(screen.getAllByAltText("image 2").length).toBeGreaterThan(1)
    expect(screen.getByLabelText("Close")).toBeInTheDocument()
    expect(screen.getByText("3 / 4")).toBeInTheDocument()
  })

  test("clicking the +N overlay opens the lightbox at the 4th image", () => {
    render(<ChatImageGallery images={makeImages(7)} />)
    fireEvent.click(screen.getByText("+3"))
    expect(screen.getByText("4 / 7")).toBeInTheDocument()
  })

  test("prev/next buttons and arrow keys navigate the gallery", () => {
    render(<ChatImageGallery images={makeImages(3)} />)
    fireEvent.click(screen.getByAltText("image 0"))
    expect(screen.getByText("1 / 3")).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText("Next image"))
    expect(screen.getByText("2 / 3")).toBeInTheDocument()

    fireEvent.keyDown(window, { key: "ArrowRight" })
    expect(screen.getByText("3 / 3")).toBeInTheDocument()

    // At the last image, the next button is hidden.
    expect(screen.queryByLabelText("Next image")).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: "ArrowLeft" })
    expect(screen.getByText("2 / 3")).toBeInTheDocument()
  })

  test("Download link tracks the active image", () => {
    render(<ChatImageGallery images={makeImages(3)} />)
    fireEvent.click(screen.getByAltText("image 1"))

    const download = screen.getByLabelText("Download") as HTMLAnchorElement
    expect(download.href).toBe("https://example.com/img-1.png")

    fireEvent.click(screen.getByLabelText("Next image"))
    const updated = screen.getByLabelText("Download") as HTMLAnchorElement
    expect(updated.href).toBe("https://example.com/img-2.png")
  })

  test("reopening the lightbox at a different tile resets to that index", () => {
    render(<ChatImageGallery images={makeImages(4)} />)
    fireEvent.click(screen.getByAltText("image 0"))
    fireEvent.click(screen.getByLabelText("Close"))

    // Tap the grid tile for image 2 (not the lightbox copy, which is now gone).
    const tile = screen.getByAltText("image 2")
    fireEvent.click(tile)
    expect(screen.getByText("3 / 4")).toBeInTheDocument()
  })

  test("single image lightbox has no prev/next or index indicator", () => {
    render(<ChatImageGallery images={makeImages(1)} />)
    fireEvent.click(screen.getByAltText("image 0"))
    expect(screen.queryByLabelText("Previous image")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Next image")).not.toBeInTheDocument()
    expect(screen.queryByText(/^\d+ \/ \d+$/)).not.toBeInTheDocument()
    expect(screen.queryByRole("tablist", { name: "Image thumbnails" })).not.toBeInTheDocument()
    expect(screen.getByLabelText("Close")).toBeInTheDocument()
  })

  test("shows a photo-count badge on every multi-image grid", () => {
    for (const n of [2, 3, 4, 7]) {
      const { unmount } = render(<ChatImageGallery images={makeImages(n)} />)
      const grid = document.querySelector(".grid") as HTMLElement
      expect(grid).not.toBeNull()
      // The badge is a sibling of the tile buttons inside the grid container.
      expect(grid.textContent).toContain(String(n))
      unmount()
    }
  })

  test("lightbox renders a thumbnail strip for multi-image sets", () => {
    render(<ChatImageGallery images={makeImages(4)} />)
    fireEvent.click(screen.getByAltText("image 0"))

    const strip = screen.getByRole("tablist", { name: "Image thumbnails" })
    expect(strip).toBeInTheDocument()
    const thumbs = screen.getAllByRole("tab")
    expect(thumbs.length).toBe(4)
    expect(thumbs[0]).toHaveAttribute("aria-selected", "true")
    expect(thumbs[1]).toHaveAttribute("aria-selected", "false")
  })

  test("clicking a thumbnail jumps the lightbox to that image", () => {
    render(<ChatImageGallery images={makeImages(4)} />)
    fireEvent.click(screen.getByAltText("image 0"))

    fireEvent.click(screen.getByLabelText("Show image 3"))
    expect(screen.getByText("3 / 4")).toBeInTheDocument()
    const thumbs = screen.getAllByRole("tab")
    expect(thumbs[2]).toHaveAttribute("aria-selected", "true")
  })

  test("collapsing the gallery replaces the grid with an 'N images' chip and persists", () => {
    const { unmount } = render(<ChatImageGallery images={makeImages(4)} />)
    fireEvent.click(screen.getByLabelText("Hide image"))

    expect(screen.queryByAltText("image 0")).not.toBeInTheDocument()
    expect(screen.getByText("4 images", { exact: false })).toBeInTheDocument()

    // Persists across a remount of the same image set.
    unmount()
    render(<ChatImageGallery images={makeImages(4)} />)
    expect(screen.queryByAltText("image 0")).not.toBeInTheDocument()

    // Expanding restores the grid.
    fireEvent.click(screen.getByText("4 images", { exact: false }))
    expect(screen.getByAltText("image 0")).toBeInTheDocument()
  })
})
