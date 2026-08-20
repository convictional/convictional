import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/composites/confirmationDialog/confirm", () => ({ confirm: vi.fn() }))
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { CommentMenu } from "~/react/features/postShow/components/CommentMenu"

const mockedConfirm = vi.mocked(confirm)

beforeEach(() => {
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function open() {
  fireEvent.click(screen.getByRole("button", { name: "Comment actions" }))
}

describe("CommentMenu", () => {
  test("authors see Copy link, Edit, and Delete", () => {
    render(<CommentMenu commentId="c1" canModify onEdit={vi.fn()} onDelete={vi.fn()} />)
    open()
    expect(screen.getByText("Copy link")).toBeInTheDocument()
    expect(screen.getByText("Edit")).toBeInTheDocument()
    expect(screen.getByText("Delete")).toBeInTheDocument()
  })

  test("non-authors only see Copy link", () => {
    render(<CommentMenu commentId="c1" canModify={false} onEdit={vi.fn()} onDelete={vi.fn()} />)
    open()
    expect(screen.getByText("Copy link")).toBeInTheDocument()
    expect(screen.queryByText("Edit")).not.toBeInTheDocument()
    expect(screen.queryByText("Delete")).not.toBeInTheDocument()
  })

  test("Copy link writes the comment hash URL to the clipboard", async () => {
    render(<CommentMenu commentId="c1" canModify onEdit={vi.fn()} onDelete={vi.fn()} />)
    open()
    fireEvent.click(screen.getByText("Copy link"))
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("#comment-c1"))
    )
  })

  test("Delete deletes only after the confirmation resolves true", async () => {
    const onDelete = vi.fn()
    mockedConfirm.mockResolvedValueOnce(true)
    render(<CommentMenu commentId="c1" canModify onEdit={vi.fn()} onDelete={onDelete} />)
    open()
    fireEvent.click(screen.getByText("Delete"))
    await waitFor(() => expect(onDelete).toHaveBeenCalled())
  })

  test("Delete does nothing when the confirmation is cancelled", async () => {
    const onDelete = vi.fn()
    mockedConfirm.mockResolvedValueOnce(false)
    render(<CommentMenu commentId="c1" canModify onEdit={vi.fn()} onDelete={onDelete} />)
    open()
    fireEvent.click(screen.getByText("Delete"))
    await waitFor(() => expect(mockedConfirm).toHaveBeenCalled())
    expect(onDelete).not.toHaveBeenCalled()
  })
})
