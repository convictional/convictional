import { afterEach, describe, expect, test, vi } from "vitest"

import { UndoToast } from "~/react/features/mailboxIndex/components/UndoToast"

import { cleanup, fireEvent, render, screen } from "../../shared/testUtils"

describe("UndoToast", () => {
  afterEach(cleanup)

  test("renders nothing when there is no action", () => {
    const { container } = render(<UndoToast action={null} onUndo={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  test("confirms the snooze target formatted in the user's timezone", () => {
    render(
      <UndoToast
        action="snooze"
        snoozedUntil="2026-05-04T13:00:00Z" // 9:00 AM EDT
        timezone="America/New_York"
        onUndo={() => {}}
      />
    )
    expect(screen.getByText("Snoozed until May 4 2026, 9:00 AM")).toBeInTheDocument()
  })

  test("falls back to a bare label when snoozedUntil is absent", () => {
    render(<UndoToast action="snooze" onUndo={() => {}} />)
    expect(screen.getByText("Snoozed")).toBeInTheDocument()
  })

  test("labels the archive action without a timestamp", () => {
    render(<UndoToast action="archive" snoozedUntil="2026-05-04T13:00:00Z" onUndo={() => {}} />)
    expect(screen.getByText("Archived")).toBeInTheDocument()
  })

  test("invokes onUndo when the button is clicked", () => {
    const onUndo = vi.fn()
    render(<UndoToast action="archive" onUndo={onUndo} />)
    fireEvent.click(screen.getByRole("button", { name: "Undo" }))
    expect(onUndo).toHaveBeenCalledOnce()
  })
})
