import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { FocusEntryForm } from "../../../../../app/javascript/react/features/mailboxIndex/components/FocusEntryForm"

afterEach(cleanup)

describe("FocusEntryForm", () => {
  test("view kind uses view copy and submits the typed criteria with a blank title", () => {
    const onSave = vi.fn()
    render(<FocusEntryForm kind="view" editingEntry={null} onSave={onSave} onCancel={vi.fn()} />)

    expect(screen.getByText("New custom view")).toBeInTheDocument()
    expect(screen.getByText("Create view")).toBeInTheDocument()
    expect(screen.getByPlaceholderText("How should your inbox be grouped?")).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText("How should your inbox be grouped?"), {
      target: { value: "Group by sender" },
    })
    fireEvent.click(screen.getByText("Create view"))

    // Title left blank → empty string, so the server auto-generates one.
    expect(onSave).toHaveBeenCalledWith({ criteria: "Group by sender", title: "" })
  })

  test("sort kind uses sort copy and passes through the title when provided", () => {
    const onSave = vi.fn()
    render(<FocusEntryForm kind="sort" editingEntry={null} onSave={onSave} onCancel={vi.fn()} />)

    expect(screen.getByText("New custom sort")).toBeInTheDocument()
    expect(screen.getByText("Create sort")).toBeInTheDocument()
    expect(screen.getByPlaceholderText("How should your inbox be ordered?")).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText("How should your inbox be ordered?"), {
      target: { value: "Most urgent first" },
    })
    fireEvent.change(screen.getByPlaceholderText("Name (optional)"), { target: { value: "Urgency" } })
    fireEvent.click(screen.getByText("Create sort"))

    expect(onSave).toHaveBeenCalledWith({ criteria: "Most urgent first", title: "Urgency" })
  })

  test("editing prefills the fields, shows edit copy, and hides suggestions", () => {
    const onSave = vi.fn()
    render(
      <FocusEntryForm
        kind="sort"
        editingEntry={{ title: "Urgency", criteria: "Most urgent first" }}
        onSave={onSave}
        onCancel={vi.fn()}
      />
    )

    expect(screen.getByText("Edit custom sort")).toBeInTheDocument()
    expect(screen.getByText("Save")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Most urgent first")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Urgency")).toBeInTheDocument()
    // Suggestion chips only appear when creating, not editing.
    expect(screen.queryByText("Quick wins")).toBeNull()
  })

  test("a suggestion chip fills the criteria field", () => {
    render(<FocusEntryForm kind="sort" editingEntry={null} onSave={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.click(screen.getByText("Urgency"))
    expect(screen.getByDisplayValue("Order by how time-sensitive each thread is")).toBeInTheDocument()
  })

  test("disables submit and ignores a second click while a save is in flight", async () => {
    let resolveSave: () => void = () => {}
    const onSave = vi.fn(() => new Promise<void>(resolve => (resolveSave = resolve)))
    render(<FocusEntryForm kind="sort" editingEntry={null} onSave={onSave} onCancel={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText("How should your inbox be ordered?"), {
      target: { value: "Most urgent first" },
    })
    const submit = screen.getByText("Create sort")
    fireEvent.click(submit)
    // A double-click must not fire a second mutation while the first is pending.
    fireEvent.click(submit)

    await waitFor(() => expect(submit.closest("button")).toBeDisabled())
    expect(onSave).toHaveBeenCalledTimes(1)

    // Once the save resolves, the button re-enables.
    resolveSave()
    await waitFor(() => expect(submit.closest("button")).not.toBeDisabled())
  })
})
