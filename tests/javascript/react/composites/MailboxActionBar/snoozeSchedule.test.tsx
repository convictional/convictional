import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  isSnoozeableAt,
  isSnoozeDayDisabled,
  snoozeValidationMessage,
} from "~/react/composites/MailboxActionBar/snoozeSchedule"
import { DateTimePicker } from "~/react/ui/DateTimePicker"

function renderSnoozePicker(onConfirm = vi.fn(), timezone: string | null = "UTC") {
  render(
    <DateTimePicker
      timezone={timezone}
      isDayDisabled={(dayIso, nowMs) => isSnoozeDayDisabled(dayIso, nowMs, timezone)}
      isConfirmable={isSnoozeableAt}
      validationMessage={snoozeValidationMessage}
      confirmLabel="Snooze"
      onConfirm={onConfirm}
    />
  )
  return onConfirm
}

const MESSAGE = "Pick a time later than now."

describe("snooze custom picker", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-07-23T15:00:00.000Z"))
  })
  afterEach(() => vi.useRealTimers())

  it("defaults to a valid future time, so selecting today is immediately confirmable", () => {
    const onConfirm = renderSnoozePicker()

    // Pick today without touching the time — the default should already be in the future.
    fireEvent.click(screen.getByRole("button", { name: "23" }))

    const snooze = screen.getByRole("button", { name: "Snooze" }) as HTMLButtonElement
    expect(snooze.disabled).toBe(false)
    expect(snooze.className).toContain("btn-primary")
    // now = 15:00 UTC, so the default is the next hour, 16:00.
    fireEvent.click(snooze)
    expect(onConfirm).toHaveBeenCalledWith("2026-07-23T16:00:00.000Z")
  })

  it("blocks a past time on today and won't confirm it", () => {
    const onConfirm = renderSnoozePicker()

    fireEvent.click(screen.getByRole("button", { name: "23" }))
    fireEvent.change(screen.getByLabelText("Time"), { target: { value: "09:00" } })

    const snooze = screen.getByRole("button", { name: "Snooze" }) as HTMLButtonElement
    expect(snooze.disabled).toBe(true)
    // Muted "disabled" styling, not the clickable-looking primary (this theme won't dim :disabled).
    expect(snooze.className).toContain("btn-disabled")
    expect(snooze.className).not.toContain("btn-primary")

    fireEvent.click(snooze)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it("surfaces the reason as a tooltip on hover of the blocked button", () => {
    renderSnoozePicker()

    fireEvent.click(screen.getByRole("button", { name: "23" }))
    fireEvent.change(screen.getByLabelText("Time"), { target: { value: "09:00" } })

    // Not shown until hovered — it's a tooltip, not inline text.
    expect(screen.queryByText(MESSAGE)).toBeNull()

    const snooze = screen.getByRole("button", { name: "Snooze" })
    // Tooltip wraps the button in a span; hover fires there even though the button is disabled.
    fireEvent.mouseEnter(snooze.parentElement as HTMLElement)
    act(() => vi.advanceTimersByTime(500))

    expect(screen.getByText(MESSAGE)).not.toBeNull()
  })

  it("allows a future time, confirms it, and shows no tooltip", () => {
    const onConfirm = renderSnoozePicker()

    fireEvent.click(screen.getByRole("button", { name: "23" }))
    fireEvent.change(screen.getByLabelText("Time"), { target: { value: "16:00" } })

    const snooze = screen.getByRole("button", { name: "Snooze" }) as HTMLButtonElement
    expect(snooze.disabled).toBe(false)
    expect(snooze.className).toContain("btn-primary")

    fireEvent.mouseEnter(snooze.parentElement as HTMLElement)
    act(() => vi.advanceTimersByTime(500))
    expect(screen.queryByText(MESSAGE)).toBeNull()

    fireEvent.click(snooze)
    expect(onConfirm).toHaveBeenCalledWith("2026-07-23T16:00:00.000Z")
  })
})

describe("snoozeValidationMessage", () => {
  it("is null until a selection exists, then flags past instants only", () => {
    const now = 1_000_000
    expect(snoozeValidationMessage(null, now)).toBeNull()
    expect(snoozeValidationMessage(now + 1, now)).toBeNull()
    expect(snoozeValidationMessage(now, now)).toBe(MESSAGE)
    expect(snoozeValidationMessage(now - 1, now)).toBe(MESSAGE)
  })
})
