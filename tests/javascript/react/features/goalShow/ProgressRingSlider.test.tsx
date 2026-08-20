import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { ProgressRingSlider } from "~/react/features/goalShow/components/ProgressRingSlider"

afterEach(cleanup)

describe("ProgressRingSlider", () => {
  test("reflects an untracked value", () => {
    render(<ProgressRingSlider value={null} onChange={vi.fn()} />)
    const slider = screen.getByRole("slider")
    expect(slider).toHaveAttribute("aria-valuetext", "Not tracked")
    expect(slider).not.toHaveAttribute("aria-valuenow")
  })

  test("reflects a tracked value as a percentage", () => {
    render(<ProgressRingSlider value={0.5} onChange={vi.fn()} />)
    const slider = screen.getByRole("slider")
    expect(slider).toHaveAttribute("aria-valuenow", "50")
    expect(slider).toHaveAttribute("aria-valuetext", "50%")
  })

  test("keyboard enters tracking at a real 0% from untracked, and End clamps to 100%", () => {
    const onChange = vi.fn()
    render(<ProgressRingSlider value={null} onChange={onChange} />)
    const slider = screen.getByRole("slider")

    // First step off untracked lands on a tracked 0% (distinct from null).
    fireEvent.keyDown(slider, { key: "ArrowRight" })
    expect(onChange).toHaveBeenLastCalledWith(0)

    fireEvent.keyDown(slider, { key: "End" })
    expect(onChange).toHaveBeenLastCalledWith(1)
  })

  test("keyboard steps down to a tracked 0%, then clears to untracked", () => {
    const onChange = vi.fn()
    render(<ProgressRingSlider value={0.05} onChange={onChange} />)

    // 0.05 → 0% (still tracked, not null).
    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowLeft" })
    expect(onChange).toHaveBeenLastCalledWith(0)

    // Stepping left off a tracked 0% clears to untracked.
    cleanup()
    render(<ProgressRingSlider value={0} onChange={onChange} />)
    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowLeft" })
    expect(onChange).toHaveBeenLastCalledWith(null)
  })
})
