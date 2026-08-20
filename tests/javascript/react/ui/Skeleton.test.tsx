import { cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { Skeleton } from "~/react/ui/Skeleton"

afterEach(cleanup)

describe("Skeleton", () => {
  test("renders the shared shimmer look", () => {
    const { container } = render(<Skeleton />)
    const el = container.firstElementChild

    expect(el).toHaveClass("animate-pulse")
    expect(el).toHaveClass("bg-base-300")
    expect(el).toHaveClass("rounded")
  })

  test("merges caller size/shape classes", () => {
    const { container } = render(<Skeleton className="h-4 w-1/2" />)
    const el = container.firstElementChild

    expect(el).toHaveClass("h-4", "w-1/2")
    // Shimmer classes are still present alongside the caller's.
    expect(el).toHaveClass("animate-pulse", "bg-base-300")
  })
})
