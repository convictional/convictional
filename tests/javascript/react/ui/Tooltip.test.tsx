import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { Tooltip } from "~/react/ui/Tooltip"

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("Tooltip", () => {
  test("shows tooltip content on hover after delay", async () => {
    render(
      <Tooltip content="Alice, Bob">
        <button>React</button>
      </Tooltip>,
    )

    const trigger = screen.getByText("React")
    fireEvent.mouseEnter(trigger.parentElement!)

    expect(screen.queryByRole("tooltip")).toBeNull()

    await act(async () => {
      vi.advanceTimersByTime(400)
    })

    expect(screen.getByRole("tooltip")).toHaveTextContent("Alice, Bob")
  })

  test("hides tooltip on mouse leave", async () => {
    render(
      <Tooltip content="Alice, Bob">
        <button>React</button>
      </Tooltip>,
    )

    const trigger = screen.getByText("React").parentElement!
    fireEvent.mouseEnter(trigger)

    await act(async () => {
      vi.advanceTimersByTime(400)
    })

    expect(screen.getByRole("tooltip")).toBeInTheDocument()

    fireEvent.mouseLeave(trigger)

    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    const tooltip = screen.queryByRole("tooltip")
    // Either unmounted or faded out
    expect(tooltip === null || tooltip.style.opacity === "0").toBe(true)
  })

  test("renders children without tooltip when content is empty", () => {
    render(
      <Tooltip content="">
        <button>React</button>
      </Tooltip>,
    )

    expect(screen.getByText("React")).toBeInTheDocument()
    fireEvent.mouseEnter(screen.getByText("React"))
    expect(screen.queryByRole("tooltip")).toBeNull()
  })

  test("renders children without tooltip when content is null", () => {
    render(
      <Tooltip content={null}>
        <button>React</button>
      </Tooltip>,
    )

    expect(screen.getByText("React")).toBeInTheDocument()
  })

  test("shows tooltip on focus for keyboard accessibility", async () => {
    render(
      <Tooltip content="Focused tooltip">
        <button>Focus me</button>
      </Tooltip>,
    )

    const trigger = screen.getByText("Focus me").parentElement!
    fireEvent.focus(trigger)

    await act(async () => {
      vi.advanceTimersByTime(400)
    })

    expect(screen.getByRole("tooltip")).toHaveTextContent("Focused tooltip")
  })
})
