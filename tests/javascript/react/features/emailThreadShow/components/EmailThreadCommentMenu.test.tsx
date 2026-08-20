import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const confirmMock = vi.fn()
vi.mock("~/react/composites/confirmationDialog/confirm", () => ({ confirm: (...a: unknown[]) => confirmMock(...a) }))

// Render the Dropdown panel inline so menu items are immediately present.
vi.mock("~/react/ui/Dropdown", () => ({
  Dropdown: ({ children }: { children: ((args: { close: () => void }) => React.ReactNode) }) => (
    <div>{children({ close: vi.fn() })}</div>
  ),
}))

import { EmailThreadCommentMenu } from "~/react/features/emailThreadShow/components/EmailThreadCommentMenu"

beforeEach(() => confirmMock.mockReset())
afterEach(cleanup)

describe("EmailThreadCommentMenu", () => {
  it("renders Edit and Delete and fires onEdit", () => {
    const onEdit = vi.fn()
    render(<EmailThreadCommentMenu onEdit={onEdit} onDelete={vi.fn()} />)

    expect(screen.getByText("Edit")).toBeTruthy()
    expect(screen.getByText("Delete")).toBeTruthy()
    fireEvent.click(screen.getByText("Edit"))
    expect(onEdit).toHaveBeenCalledOnce()
  })

  it("confirms before deleting and only calls onDelete when confirmed", async () => {
    const onDelete = vi.fn().mockResolvedValue(undefined)

    confirmMock.mockResolvedValueOnce(false)
    render(<EmailThreadCommentMenu onEdit={vi.fn()} onDelete={onDelete} />)
    fireEvent.click(screen.getByText("Delete"))
    await waitFor(() => expect(confirmMock).toHaveBeenCalledOnce())
    expect(onDelete).not.toHaveBeenCalled()

    confirmMock.mockResolvedValueOnce(true)
    fireEvent.click(screen.getByText("Delete"))
    await waitFor(() => expect(onDelete).toHaveBeenCalledOnce())
  })
})
