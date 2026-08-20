import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { CollectionForm } from "~/react/composites/meetings/CollectionForm"

afterEach(cleanup)

describe("CollectionForm", () => {
  test("submits the trimmed title and description", async () => {
    const onSubmit = vi.fn().mockResolvedValue(null)
    render(<CollectionForm submitLabel="Create" onSubmit={onSubmit} onCancel={vi.fn()} />)

    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "  Sales  " } })
    fireEvent.change(screen.getByLabelText("Description (optional)"), { target: { value: "  calls  " } })
    fireEvent.click(screen.getByRole("button", { name: "Create" }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("Sales", "calls"))
  })

  test("passes null description when left blank", async () => {
    const onSubmit = vi.fn().mockResolvedValue(null)
    render(<CollectionForm submitLabel="Create" onSubmit={onSubmit} onCancel={vi.fn()} />)

    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Sales" } })
    fireEvent.click(screen.getByRole("button", { name: "Create" }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("Sales", null))
  })

  test("does not submit when the title is blank", () => {
    const onSubmit = vi.fn().mockResolvedValue(null)
    render(<CollectionForm submitLabel="Create" onSubmit={onSubmit} onCancel={vi.fn()} />)

    fireEvent.click(screen.getByRole("button", { name: "Create" }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  test("surfaces the error message returned by onSubmit", async () => {
    const onSubmit = vi.fn().mockResolvedValue("Name already taken")
    render(<CollectionForm submitLabel="Create" onSubmit={onSubmit} onCancel={vi.fn()} />)

    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Dupe" } })
    fireEvent.click(screen.getByRole("button", { name: "Create" }))

    expect(await screen.findByText("Name already taken")).toBeInTheDocument()
  })

  test("prefills the inputs for editing and uses the given submit label", () => {
    render(
      <CollectionForm
        initialTitle="Weekly Sync"
        initialDescription="Mondays"
        submitLabel="Save"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    expect(screen.getByLabelText("Title")).toHaveValue("Weekly Sync")
    expect(screen.getByLabelText("Description (optional)")).toHaveValue("Mondays")
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument()
  })

  test("invokes onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn()
    render(<CollectionForm submitLabel="Create" onSubmit={vi.fn()} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onCancel).toHaveBeenCalled()
  })
})
