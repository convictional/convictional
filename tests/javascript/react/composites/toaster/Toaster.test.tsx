import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { Toaster } from "~/react/composites/toaster/Toaster"
import { toastStore } from "~/react/shared/stores/toast"

beforeEach(() => {
  toastStore.setState({ toasts: [] })
  vi.useFakeTimers()
})

afterEach(() => {
  cleanup()
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
})

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

// Replaces window.location with an href-only stub and returns a restore fn so
// the swap doesn't leak into later tests in this file.
function stubLocationHref() {
  const assign = vi.fn()
  const original = Object.getOwnPropertyDescriptor(window, "location")
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      origin: "https://example.test",
      set href(value: string) {
        assign(value)
      },
    },
  })
  return { assign, restore: () => original && Object.defineProperty(window, "location", original) }
}

describe("Toaster", () => {
  test("renders nothing when there are no toasts", () => {
    const { container } = render(<Toaster />)
    expect(container).toBeEmptyDOMElement()
  })

  test("non-persistent toast auto-dismisses after 3s plus its leave transition", () => {
    render(<Toaster />)
    act(() => {
      toastStore.getState().show({ message: "Saved", level: "success", persistent: false })
    })

    expect(screen.getByText("Saved")).toBeInTheDocument()
    // fill-bar present for timed toasts
    expect(document.querySelector(".animate-\\[fillBar_3s_linear_forwards\\]")).not.toBeNull()

    advance(3000) // auto-dismiss fires, begins leave transition
    advance(200) // leave transition completes, store drops it

    expect(screen.queryByText("Saved")).not.toBeInTheDocument()
    expect(toastStore.getState().toasts).toHaveLength(0)
  })

  test("persistent toast renders no fill-bar and survives the timer", () => {
    render(<Toaster />)
    act(() => {
      toastStore.getState().show({ message: "Session changed", level: "error", persistent: true })
    })

    expect(document.querySelector(".animate-\\[fillBar_3s_linear_forwards\\]")).toBeNull()

    advance(10000)

    expect(screen.getByText("Session changed")).toBeInTheDocument()
    expect(toastStore.getState().toasts).toHaveLength(1)
  })

  test("clicking a toast with a url navigates", () => {
    const { assign, restore } = stubLocationHref()
    try {
      render(<Toaster />)
      act(() => {
        toastStore.getState().show({
          message: "Click me",
          level: "error",
          url: "https://example.test/reload",
          persistent: true,
        })
      })

      fireEvent.click(screen.getByText("Click me"))
      expect(assign).toHaveBeenCalledWith("https://example.test/reload")
    } finally {
      restore()
    }
  })

  test("ignores an unsafe javascript: url and dismisses instead", () => {
    const { assign, restore } = stubLocationHref()
    try {
      render(<Toaster />)
      act(() => {
        toastStore.getState().show({
          message: "Sketchy",
          level: "error",
          url: "javascript:alert(1)",
          persistent: true,
        })
      })

      fireEvent.click(screen.getByText("Sketchy"))
      expect(assign).not.toHaveBeenCalled()
      advance(200)
      expect(screen.queryByText("Sketchy")).not.toBeInTheDocument()
    } finally {
      restore()
    }
  })

  test("Dismiss button removes the toast via keyboard without navigating", () => {
    const { assign, restore } = stubLocationHref()
    try {
      render(<Toaster />)
      act(() => {
        toastStore.getState().show({
          message: "Session changed",
          level: "error",
          url: "https://example.test/reload",
          persistent: true,
        })
      })

      // Real, focusable control — unlike the old clickable <div>.
      fireEvent.click(screen.getByRole("button", { name: "Dismiss" }))
      expect(assign).not.toHaveBeenCalled() // stopPropagation: no card navigation
      advance(200)
      expect(screen.queryByText("Session changed")).not.toBeInTheDocument()
    } finally {
      restore()
    }
  })

  test("error uses role=alert (assertive) and success uses role=status (polite)", () => {
    render(<Toaster />)
    act(() => {
      toastStore.getState().show({ message: "Boom", level: "error", persistent: true })
      toastStore.getState().show({ message: "Yay", level: "success", persistent: true })
    })

    expect(screen.getByRole("alert")).toHaveTextContent("Boom")
    expect(screen.getByRole("status")).toHaveTextContent("Yay")
  })

  test("clicking a toast without a url dismisses it", () => {
    render(<Toaster />)
    act(() => {
      toastStore.getState().show({ message: "Dismiss me", level: "success", persistent: true })
    })

    fireEvent.click(screen.getByText("Dismiss me"))
    advance(200)

    expect(screen.queryByText("Dismiss me")).not.toBeInTheDocument()
    expect(toastStore.getState().toasts).toHaveLength(0)
  })

  test("error and success render distinct icons and palettes", () => {
    render(<Toaster />)
    act(() => {
      toastStore.getState().show({ message: "Boom", level: "error", persistent: true })
      toastStore.getState().show({ message: "Yay", level: "success", persistent: true })
    })

    expect(screen.getByText("error")).toBeInTheDocument() // error icon glyph
    expect(screen.getByText("check")).toBeInTheDocument() // success icon glyph
    expect(document.querySelector(".text-error-content")).not.toBeNull()
    expect(document.querySelector(".text-success-content")).not.toBeNull()
  })
})
