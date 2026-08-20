import { renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { useRefocusOnEditClose } from "~/react/shared/hooks/useRefocusOnEditClose"

describe("useRefocusOnEditClose", () => {
  it("focuses only on the transition from editing to not-editing", () => {
    const focus = vi.fn()
    const { rerender } = renderHook(({ id }: { id: string | null }) => useRefocusOnEditClose(id, focus), {
      initialProps: { id: null as string | null },
    })
    // Mount with nothing editing — no focus.
    expect(focus).not.toHaveBeenCalled()

    // Enter edit mode — still no focus (we only refocus on close).
    rerender({ id: "c1" })
    expect(focus).not.toHaveBeenCalled()

    // Close the edit — focus returns to the composer.
    rerender({ id: null })
    expect(focus).toHaveBeenCalledOnce()

    // Switching directly between two edited items does not refocus.
    rerender({ id: "c2" })
    rerender({ id: "c3" })
    expect(focus).toHaveBeenCalledOnce()
  })

  it("does not focus when it was never editing", () => {
    const focus = vi.fn()
    const { rerender } = renderHook(({ id }: { id: string | null }) => useRefocusOnEditClose(id, focus), {
      initialProps: { id: null as string | null },
    })
    rerender({ id: null })
    expect(focus).not.toHaveBeenCalled()
  })
})
