import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { Dialog } from "~/react/ui/Dialog"

afterEach(cleanup)

function Harness({
  initialOpen = true,
  onCloseSpy,
  labelledBy,
  testId,
  overlayZIndexClassName,
}: {
  initialOpen?: boolean
  onCloseSpy?: () => void
  labelledBy?: string
  testId?: string
  overlayZIndexClassName?: string
}) {
  const [isOpen, setIsOpen] = useState(initialOpen)
  return (
    <Dialog
      isOpen={isOpen}
      onClose={() => {
        setIsOpen(false)
        onCloseSpy?.()
      }}
      labelledBy={labelledBy}
      testId={testId}
      overlayZIndexClassName={overlayZIndexClassName}
    >
      <h3 id="dialog-title">Dialog title</h3>
      <p>Dialog body</p>
      <button type="button">Action</button>
    </Dialog>
  )
}

describe("Dialog", () => {
  test("renders children when isOpen is true", () => {
    render(<Harness testId="my-dialog" />)
    expect(screen.getByText("Dialog body")).toBeInTheDocument()
    expect(screen.getByTestId("my-dialog")).toBeInTheDocument()
  })

  test("renders nothing when isOpen is false", () => {
    render(<Harness initialOpen={false} testId="my-dialog" />)
    expect(screen.queryByText("Dialog body")).not.toBeInTheDocument()
    expect(screen.queryByTestId("my-dialog")).not.toBeInTheDocument()
  })

  test("calls onClose when Escape is pressed", () => {
    const onCloseSpy = vi.fn()
    render(<Harness onCloseSpy={onCloseSpy} testId="my-dialog" />)

    fireEvent.keyDown(document.body, { key: "Escape" })

    expect(onCloseSpy).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId("my-dialog")).not.toBeInTheDocument()
  })

  test("calls onClose when the backdrop is clicked", () => {
    const onCloseSpy = vi.fn()
    render(<Harness onCloseSpy={onCloseSpy} testId="my-dialog" />)

    const floating = screen.getByTestId("my-dialog")
    // FloatingOverlay is the floating element's parent (FloatingFocusManager
    // wraps the content in a focus guard but the overlay handles outside-press).
    const overlay = floating.closest("[class*='items-center']") as HTMLElement
    expect(overlay).toBeTruthy()

    fireEvent.pointerDown(overlay, { button: 0 })
    fireEvent.mouseDown(overlay, { button: 0 })
    fireEvent.click(overlay, { button: 0 })

    expect(onCloseSpy).toHaveBeenCalled()
    expect(screen.queryByTestId("my-dialog")).not.toBeInTheDocument()
  })

  test("sets aria-labelledby and role=dialog on the floating element", () => {
    render(<Harness labelledBy="dialog-title" testId="my-dialog" />)

    const floating = screen.getByTestId("my-dialog")
    expect(floating).toHaveAttribute("aria-labelledby", "dialog-title")
    expect(floating).toHaveAttribute("role", "dialog")
  })

  test("applies testId to the floating content element", () => {
    render(<Harness testId="custom-dialog" />)

    const floating = screen.getByTestId("custom-dialog")
    expect(floating).toBeInTheDocument()
    expect(floating).toHaveTextContent("Dialog body")
  })

  test("defaults the overlay z-index to z-50 and overrides it via overlayZIndexClassName", () => {
    const { unmount } = render(<Harness testId="my-dialog" />)

    let overlay = screen
      .getByTestId("my-dialog")
      .closest("[class*='items-center']") as HTMLElement
    expect(overlay).toBeTruthy()
    expect(overlay.className).toContain("z-50")
    expect(overlay.className).not.toContain("z-[90]")
    expect(overlay.className).toContain("overlay-backdrop")

    unmount()

    render(<Harness testId="my-dialog" overlayZIndexClassName="z-[90]" />)

    overlay = screen.getByTestId("my-dialog").closest("[class*='items-center']") as HTMLElement
    expect(overlay).toBeTruthy()
    expect(overlay.className).toContain("z-[90]")
    expect(overlay.className).not.toContain("z-50")
    expect(overlay.className).toContain("overlay-backdrop")
  })
})
