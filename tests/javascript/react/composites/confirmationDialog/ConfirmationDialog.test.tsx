import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { ConfirmationDialog } from "../../../../../app/javascript/react/composites/confirmationDialog/ConfirmationDialog"
import {
  confirmationDialogStore,
  type ConfirmationRequest,
} from "../../../../../app/javascript/react/composites/confirmationDialog/store"

function openRequest(overrides: Partial<ConfirmationRequest> = {}) {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  act(() => {
    confirmationDialogStore.getState().open({
      message: "Delete this thing?",
      onConfirm,
      onCancel,
      ...overrides,
    })
  })
  return { onConfirm, onCancel }
}

describe("ConfirmationDialog", () => {
  beforeEach(() => {
    act(() => {
      confirmationDialogStore.setState({ current: null })
    })
  })
  afterEach(cleanup)

  test("renders nothing when no request is open", () => {
    render(<ConfirmationDialog />)
    expect(screen.queryByTestId("confirmation-dialog")).toBeNull()
  })

  test("renders message and default labels when a request opens", () => {
    render(<ConfirmationDialog />)
    openRequest()

    expect(screen.getByTestId("confirmation-dialog")).toBeInTheDocument()
    expect(screen.getByText("Delete this thing?")).toBeInTheDocument()
    expect(screen.getByTestId("confirmation-dialog-confirm")).toHaveTextContent("Confirm")
    expect(screen.getByTestId("confirmation-dialog-cancel")).toHaveTextContent("Cancel")
  })

  test("custom title and labels render", () => {
    render(<ConfirmationDialog />)
    openRequest({ title: "Heads up", confirmLabel: "Yes", cancelLabel: "No" })
    expect(screen.getByText("Heads up")).toBeInTheDocument()
    expect(screen.getByTestId("confirmation-dialog-confirm")).toHaveTextContent("Yes")
    expect(screen.getByTestId("confirmation-dialog-cancel")).toHaveTextContent("No")
  })

  test("clicking Confirm runs onConfirm and clears the request", () => {
    render(<ConfirmationDialog />)
    const { onConfirm, onCancel } = openRequest()

    fireEvent.click(screen.getByTestId("confirmation-dialog-confirm"))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()
    expect(confirmationDialogStore.getState().current).toBeNull()
  })

  test("clicking Cancel runs onCancel and clears the request", () => {
    render(<ConfirmationDialog />)
    const { onConfirm, onCancel } = openRequest()

    fireEvent.click(screen.getByTestId("confirmation-dialog-cancel"))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
    expect(confirmationDialogStore.getState().current).toBeNull()
  })

  test("pressing Escape rejects the request", () => {
    render(<ConfirmationDialog />)
    const { onCancel } = openRequest()

    fireEvent.keyDown(document.body, { key: "Escape" })
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(confirmationDialogStore.getState().current).toBeNull()
  })

  test("renders its overlay above the z-50 modal band", () => {
    render(<ConfirmationDialog />)
    openRequest()

    const overlay = screen
      .getByTestId("confirmation-dialog")
      .closest("[class*='items-center']") as HTMLElement
    expect(overlay).toBeTruthy()
    expect(overlay.className).toContain("z-[90]")
    expect(overlay.className).not.toContain("z-50")
    expect(screen.getByTestId("confirmation-dialog")).toBeInTheDocument()
  })

  test("opening a second request while one is open cancels the first", () => {
    render(<ConfirmationDialog />)
    const first = openRequest()
    const second = openRequest({ message: "Second?" })

    expect(first.onCancel).toHaveBeenCalledTimes(1)
    expect(screen.getByText("Second?")).toBeInTheDocument()

    fireEvent.click(screen.getByTestId("confirmation-dialog-confirm"))
    expect(second.onConfirm).toHaveBeenCalledTimes(1)
  })
})
