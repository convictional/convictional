import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Avatar } from "~/react/ui/Avatar"

const NOLAN = "https://cdn.example/nolan.png"
const LINNEA = "https://cdn.example/linnea.png"

describe("Avatar", () => {
  it("swaps to the new user's image without showing the previous one, and clears a prior load error", () => {
    const { container, rerender } = render(<Avatar displayName="Nolan Ridgeway" picture={NOLAN} />)

    // Nolan's image renders initially.
    const nolanImg = container.querySelector("img")!
    expect(nolanImg).toHaveAttribute("src", NOLAN)
    expect(nolanImg).toHaveAttribute("alt", "Nolan Ridgeway")

    // Re-rendering with the same picture URL keeps the same <img> node so the browser
    // cache serves it instantly (the ORB re-mount benefit). This only catches a
    // per-render-unstable key (e.g. Math.random()); the NOLAN→LINNEA not.toBe below is
    // what pins the key to `picture` specifically.
    rerender(<Avatar displayName="Nolan Ridgeway" picture={NOLAN} />)
    expect(container.querySelector("img")!).toBe(nolanImg)

    // Nolan's image fails to load: fall back to his initial and hide the <img>.
    fireEvent.error(nolanImg)
    expect(screen.getByText("N")).toBeInTheDocument()
    expect(nolanImg.style.display).toBe("none")

    // Switching to a different user must reset the error state and show their image.
    rerender(<Avatar displayName="Linnea McAlister" picture={LINNEA} />)

    const linneaImg = container.querySelector("img")!
    expect(linneaImg.style.display).not.toBe("none")
    expect(linneaImg).toHaveAttribute("src", LINNEA)
    expect(linneaImg).toHaveAttribute("alt", "Linnea McAlister")

    // The primary picture-key guard: the `picture` key forces a remount on URL change,
    // discarding the stale bitmap, so the new <img> is a distinct DOM node from the failed one.
    expect(linneaImg).not.toBe(nolanImg)

    // Nolan's fallback initial must be gone.
    expect(container).not.toHaveTextContent("N")
  })

  it("renders the display-name initial and no image when picture is null", () => {
    render(<Avatar displayName="Briar Nakamura" picture={null} />)

    expect(screen.queryByRole("img")).toBeNull()
    expect(screen.getByText("B")).toBeInTheDocument()
  })
})
