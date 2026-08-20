import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { DraftConflictDialog } from "~/react/features/emailThreadShow/components/DraftConflictDialog"

afterEach(() => cleanup())

describe("DraftConflictDialog", () => {
  it("does not render when closed", () => {
    const { container } = render(
      <DraftConflictDialog
        open={false}
        replyType="reply"
        replyUrl="/r"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(container.innerHTML).toBe("")
  })

  it("clicks Replace draft -> onConfirm fires", () => {
    const onConfirm = vi.fn()
    render(
      <DraftConflictDialog open replyType="reply_all" replyUrl="/r" onConfirm={onConfirm} onCancel={vi.fn()} />
    )
    fireEvent.click(screen.getByText("Replace draft"))
    expect(onConfirm).toHaveBeenCalled()
  })

  it("clicks Cancel -> onCancel fires", () => {
    const onCancel = vi.fn()
    render(<DraftConflictDialog open replyType="reply" replyUrl="/r" onConfirm={vi.fn()} onCancel={onCancel} />)
    fireEvent.click(screen.getByText("Cancel"))
    expect(onCancel).toHaveBeenCalled()
  })
})
