import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { CopyTimestampButton } from "~/react/features/meetingShow/components/CopyTimestampButton"

const writeText = vi.fn().mockResolvedValue(undefined)

beforeEach(() => {
  writeText.mockClear()
  Object.assign(navigator, { clipboard: { writeText } })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("CopyTimestampButton", () => {
  test("copies a deep link at the current second and formats the label", () => {
    // 754s = 12:34, which is also the example in the component comment.
    render(<CopyTimestampButton meetingId="m1" currentTime={754} />)

    expect(screen.getByRole("button", { name: /Copy link at 12:34/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button"))

    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("/meetings/m1#timestamp-754"))
  })

  test("formats hours when the timestamp is over an hour", () => {
    render(<CopyTimestampButton meetingId="m1" currentTime={3661} />)
    expect(screen.getByRole("button", { name: /Copy link at 1:01:01/ })).toBeInTheDocument()
  })

  test("shows the copied state, then reverts after the timeout", () => {
    vi.useFakeTimers()
    render(<CopyTimestampButton meetingId="m1" currentTime={10} />)

    expect(screen.getByText("link")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button"))
    expect(screen.getByText("check")).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(screen.getByText("link")).toBeInTheDocument()
  })
})
