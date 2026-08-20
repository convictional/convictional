import { renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { useScrollIntoViewOnEdit } from "~/react/shared/hooks/useScrollIntoViewOnEdit"

describe("useScrollIntoViewOnEdit", () => {
  it("scrolls the element into view only when it enters edit mode", () => {
    const scrollIntoView = vi.fn()
    const { result, rerender } = renderHook(
      ({ editing }: { editing: boolean }) => useScrollIntoViewOnEdit<HTMLDivElement>(editing),
      { initialProps: { editing: false } }
    )
    // Attach a fake element to the returned ref; the mount effect already ran with
    // editing=false, so nothing has scrolled yet.
    result.current.current = { scrollIntoView } as unknown as HTMLDivElement
    expect(scrollIntoView).not.toHaveBeenCalled()

    rerender({ editing: true })
    expect(scrollIntoView).toHaveBeenCalledOnce()
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest", behavior: "smooth" })

    // Leaving edit mode does not scroll.
    scrollIntoView.mockClear()
    rerender({ editing: false })
    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it("no-ops without throwing when the ref is unattached", () => {
    const { rerender } = renderHook(({ editing }: { editing: boolean }) => useScrollIntoViewOnEdit(editing), {
      initialProps: { editing: false },
    })
    expect(() => rerender({ editing: true })).not.toThrow()
  })
})
