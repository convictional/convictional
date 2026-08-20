import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { Goal } from "~/react/shared/types"

const apiFetch = vi.fn()
vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}))

import { EditableGoalDescription, EditableGoalTitle } from "~/react/features/goalShow/components/GoalHeadingEditors"

const goal = { id: "g1", title: "My title", description: "My description" } as unknown as Goal

function lastBody() {
  const [, options] = apiFetch.mock.calls.at(-1) as [string, { body: string }]
  return JSON.parse(options.body)
}

beforeEach(() => {
  apiFetch.mockReset()
  apiFetch.mockResolvedValue({ ...goal })
})
afterEach(cleanup)

describe("EditableGoalTitle", () => {
  test("PATCHes the title on Enter and reports the updated goal", async () => {
    const onGoalUpdated = vi.fn()
    apiFetch.mockResolvedValueOnce({ ...goal, title: "Renamed" })
    render(<EditableGoalTitle goal={goal} onGoalUpdated={onGoalUpdated} />)

    fireEvent.click(screen.getByText("My title"))
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Renamed" } })
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" })

    await waitFor(() => expect(apiFetch).toHaveBeenCalled())
    expect(apiFetch.mock.calls[0][0]).toContain("/api/goals/g1")
    expect(lastBody()).toEqual({ title: "Renamed" })
    await waitFor(() => expect(onGoalUpdated).toHaveBeenCalledWith({ ...goal, title: "Renamed" }))
  })

  test("does not save an unchanged or empty title", async () => {
    render(<EditableGoalTitle goal={goal} onGoalUpdated={vi.fn()} />)

    fireEvent.click(screen.getByText("My title"))
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } })
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" })

    expect(apiFetch).not.toHaveBeenCalled()
  })

  test("Escape cancels without saving", () => {
    render(<EditableGoalTitle goal={goal} onGoalUpdated={vi.fn()} />)

    fireEvent.click(screen.getByText("My title"))
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Discarded" } })
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Escape" })

    expect(apiFetch).not.toHaveBeenCalled()
    expect(screen.getByText("My title")).toBeInTheDocument()
  })
})

describe("EditableGoalDescription", () => {
  test("PATCHes the description on Enter", async () => {
    const onGoalUpdated = vi.fn()
    apiFetch.mockResolvedValueOnce({ ...goal, description: "Updated" })
    render(<EditableGoalDescription goal={goal} onGoalUpdated={onGoalUpdated} />)

    fireEvent.click(screen.getByText("My description"))
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Updated" } })
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" })

    await waitFor(() => expect(apiFetch).toHaveBeenCalled())
    expect(lastBody()).toEqual({ description: "Updated" })
    await waitFor(() => expect(onGoalUpdated).toHaveBeenCalledWith({ ...goal, description: "Updated" }))
  })

  test("Shift+Enter inserts a newline instead of saving", () => {
    render(<EditableGoalDescription goal={goal} onGoalUpdated={vi.fn()} />)

    fireEvent.click(screen.getByText("My description"))
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", shiftKey: true })

    expect(apiFetch).not.toHaveBeenCalled()
  })
})
