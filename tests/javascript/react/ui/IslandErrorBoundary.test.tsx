import * as Sentry from "@sentry/browser"
import { cleanup, render, screen, fireEvent } from "@testing-library/react"
import { afterAll, afterEach, describe, expect, test, vi } from "vitest"

import { IslandErrorBoundary } from "~/react/ui/IslandErrorBoundary"

vi.mock("@sentry/browser", () => ({ withScope: vi.fn() }))

// Suppress React's console.error for expected error boundary triggers
const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})

afterEach(() => {
  cleanup()
  consoleError.mockClear()
})

afterAll(() => {
  consoleError.mockRestore()
})

function ThrowOnce({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("test error")
  return <div>child content</div>
}

describe("IslandErrorBoundary", () => {
  test("renders children when there is no error", () => {
    render(
      <IslandErrorBoundary>
        <div>hello</div>
      </IslandErrorBoundary>
    )
    expect(screen.getByText("hello")).toBeTruthy()
  })

  test("renders error message when a child throws", () => {
    render(
      <IslandErrorBoundary>
        <ThrowOnce shouldThrow />
      </IslandErrorBoundary>
    )
    expect(screen.getByText("Something went wrong.")).toBeTruthy()
    expect(screen.getByText("Try again")).toBeTruthy()
    expect(screen.queryByText("child content")).toBeNull()
  })

  test("logs the error to console", () => {
    render(
      <IslandErrorBoundary>
        <ThrowOnce shouldThrow />
      </IslandErrorBoundary>
    )
    expect(consoleError).toHaveBeenCalledWith("[React Island]", expect.any(Error))
  })

  test("recovers when 'Try again' is clicked and child no longer throws", () => {
    const { rerender } = render(
      <IslandErrorBoundary>
        <ThrowOnce shouldThrow />
      </IslandErrorBoundary>
    )
    expect(screen.getByText("Something went wrong.")).toBeTruthy()

    // Re-render with a child that won't throw, then click retry
    rerender(
      <IslandErrorBoundary>
        <ThrowOnce shouldThrow={false} />
      </IslandErrorBoundary>
    )
    fireEvent.click(screen.getByText("Try again"))

    expect(screen.getByText("child content")).toBeTruthy()
    expect(screen.queryByText("Something went wrong.")).toBeNull()
  })

  test("re-enters error state when retry is clicked but child still throws", () => {
    render(
      <IslandErrorBoundary>
        <ThrowOnce shouldThrow />
      </IslandErrorBoundary>
    )
    expect(screen.getByText("Something went wrong.")).toBeTruthy()

    fireEvent.click(screen.getByText("Try again"))

    expect(screen.getByText("Something went wrong.")).toBeTruthy()
    expect(screen.queryByText("child content")).toBeNull()
  })

  test("forwards error to Sentry", () => {
    const captureException = vi.fn()
    const setContext = vi.fn()
    vi.mocked(Sentry.withScope).mockImplementation((cb: (scope: any) => void) =>
      cb({ setContext, captureException })
    )

    render(
      <IslandErrorBoundary>
        <ThrowOnce shouldThrow />
      </IslandErrorBoundary>
    )

    expect(Sentry.withScope).toHaveBeenCalled()
    expect(setContext).toHaveBeenCalledWith("react", {
      componentStack: expect.any(String),
    })
    expect(captureException).toHaveBeenCalledWith(expect.any(Error))
  })
})
