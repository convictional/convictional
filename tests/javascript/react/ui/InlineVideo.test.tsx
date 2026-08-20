import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { InlineVideo } from "~/react/ui/InlineVideo"

afterEach(cleanup)

describe("InlineVideo", () => {
  test("renders a video with the given src and an aria-label from the title", () => {
    const { container } = render(<InlineVideo src="https://example.com/demo.mp4" title="demo.mp4" />)

    const video = container.querySelector("video") as HTMLVideoElement
    expect(video).toBeInTheDocument()
    expect(video.getAttribute("src")).toBe("https://example.com/demo.mp4")
    expect(video.hasAttribute("controls")).toBe(true)
    expect(video.getAttribute("aria-label")).toBe("demo.mp4")
  })

  test("exposes a download fallback anchor pointing at the src", () => {
    render(<InlineVideo src="https://example.com/demo.mp4" title="demo.mp4" />)

    const fallback = screen.getByRole("link", { hidden: true }) as HTMLAnchorElement
    expect(fallback.getAttribute("href")).toBe("https://example.com/demo.mp4")
  })

  test("swaps the player for a download link when the media fails to decode", () => {
    const { container } = render(<InlineVideo src="https://example.com/demo.mp4" title="demo.mp4" />)

    fireEvent.error(container.querySelector("video") as HTMLVideoElement)

    expect(container.querySelector("video")).toBeNull()
    const link = screen.getByRole("link") as HTMLAnchorElement
    expect(link.getAttribute("href")).toBe("https://example.com/demo.mp4")
    expect(link.textContent).toBe("demo.mp4")
  })
})
