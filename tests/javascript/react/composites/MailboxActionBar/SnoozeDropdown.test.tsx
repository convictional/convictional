import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { SnoozeDropdown } from "~/react/composites/MailboxActionBar/SnoozeDropdown"

import { cleanup, fireEvent, render, screen } from "../../shared/testUtils"

// A fixed clock so the calendar opens on a known month and "today" is deterministic.
// 2026-07-21T12:00:00Z — with a UTC timezone prop, today is 2026-07-21.
const NOW = new Date("2026-07-21T12:00:00Z")

// The confirm button and the icon-only trigger share the accessible name "Snooze";
// the trigger's text is the lowercase material-icon ligature, the confirm's is "Snooze".
function confirmButton(): HTMLButtonElement {
  const button = screen
    .getAllByRole("button", { name: "Snooze" })
    .find((b): b is HTMLButtonElement => b.textContent === "Snooze")
  if (!button) throw new Error("No confirm button")
  return button
}

// Open the popover on the preset list, then step into the custom date/time view.
function openCustomView() {
  fireEvent.click(screen.getByRole("menuitem", { name: /Custom/i }))
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
  cleanup()
})

describe("SnoozeDropdown custom date/time picker", () => {
  test("shows presets and a Custom option, with the picker hidden until chosen", () => {
    render(<SnoozeDropdown isOpen onOpenChange={() => {}} onSnooze={() => {}} timezone="UTC" />)

    expect(screen.getByText(/Two hours from now/i)).toBeInTheDocument()
    expect(screen.getByRole("menuitem", { name: /Custom/i })).toBeInTheDocument()
    // The calendar only appears after choosing "Custom"; "Su" is unique to its grid.
    expect(screen.queryByText("Su")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Time")).not.toBeInTheDocument()
  })

  test("Custom takes over the popover, and Back returns to the preset list", () => {
    render(<SnoozeDropdown isOpen onOpenChange={() => {}} onSnooze={() => {}} timezone="UTC" />)

    openCustomView()

    // Picker is shown; presets are replaced.
    expect(screen.getByText("Su")).toBeInTheDocument()
    expect(screen.getByLabelText("Time")).toBeInTheDocument()
    expect(screen.queryByText(/Two hours from now/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Back to snooze options/i }))

    // Back on the preset list; the calendar is gone again.
    expect(screen.getByText(/Two hours from now/i)).toBeInTheDocument()
    expect(screen.queryByText("Su")).not.toBeInTheDocument()
  })

  test("confirm is disabled until a date is picked, then snoozes to the chosen tz-aware instant", () => {
    const onSnooze = vi.fn()
    const onOpenChange = vi.fn()
    render(<SnoozeDropdown isOpen onOpenChange={onOpenChange} onSnooze={onSnooze} timezone="UTC" />)

    openCustomView()

    // A seeded time with no date can't be snoozed.
    expect(confirmButton()).toBeDisabled()

    // Pick a future day in the current (July 2026) month. Day 22 is tomorrow.
    fireEvent.click(screen.getByRole("button", { name: "22" }))
    // Set the time explicitly rather than relying on the seeded default, which is now the
    // next full hour (nextHourTimeInZone) instead of a fixed 09:00.
    fireEvent.change(screen.getByLabelText("Time"), { target: { value: "09:00" } })
    expect(confirmButton()).toBeEnabled()

    fireEvent.click(confirmButton())

    // 2026-07-22 at 09:00 in UTC.
    expect(onSnooze).toHaveBeenCalledWith("2026-07-22T09:00:00.000Z")
    // Picking closes the popover, same exit path as a preset.
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test("past days are disabled in the grid", () => {
    render(<SnoozeDropdown isOpen onOpenChange={() => {}} onSnooze={() => {}} timezone="UTC" />)

    openCustomView()

    // Day 20 (yesterday) is in the past and can't be selected; day 22 (tomorrow) can.
    expect(screen.getByRole("button", { name: "20" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "22" })).toBeEnabled()
  })
})
