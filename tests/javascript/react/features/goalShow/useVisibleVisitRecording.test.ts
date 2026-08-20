import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// Capture the id passed to the shared recorder on each call.
const recordVisit = vi.fn()
vi.mock("~/react/shared/hooks/useVisitRecording", () => ({
  useWorkspaceVisitRecording: () => recordVisit,
}))

import { useVisibleVisitRecording } from "~/react/features/goalShow/hooks/useVisibleVisitRecording"

let visibility: DocumentVisibilityState = "visible"

function setVisibility(next: DocumentVisibilityState) {
  visibility = next
  document.dispatchEvent(new Event("visibilitychange"))
}

beforeEach(() => {
  visibility = "visible"
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility)
})
afterEach(() => vi.clearAllMocks())

describe("useVisibleVisitRecording", () => {
  test("records the newest event on load when visible and ready", () => {
    renderHook(() => useVisibleVisitRecording("ws-1", "e1", true))
    expect(recordVisit).toHaveBeenCalledExactlyOnceWith("e1")
  })

  test("does not record until ready, nor with no event", () => {
    const { rerender } = renderHook(({ id, ready }) => useVisibleVisitRecording("ws-1", id, ready), {
      initialProps: { id: null as string | null, ready: false },
    })
    expect(recordVisit).not.toHaveBeenCalled()

    rerender({ id: "e1", ready: false })
    expect(recordVisit).not.toHaveBeenCalled()

    rerender({ id: "e1", ready: true })
    expect(recordVisit).toHaveBeenCalledExactlyOnceWith("e1")
  })

  test("a hidden tab does not record; it catches up on return to visible", () => {
    visibility = "hidden"
    const { rerender } = renderHook(({ id }) => useVisibleVisitRecording("ws-1", id, true), {
      initialProps: { id: "e1" as string | null },
    })
    expect(recordVisit).not.toHaveBeenCalled()

    // A live event arrives while hidden — still no record.
    rerender({ id: "e2" })
    expect(recordVisit).not.toHaveBeenCalled()

    // Returning to the tab catches up to the newest event, once.
    act(() => setVisibility("visible"))
    expect(recordVisit).toHaveBeenCalledExactlyOnceWith("e2")
  })

  test("records each new event once; ignores visibility toggles with no new event", () => {
    const { rerender } = renderHook(({ id }) => useVisibleVisitRecording("ws-1", id, true), {
      initialProps: { id: "e1" as string | null },
    })
    expect(recordVisit).toHaveBeenCalledExactlyOnceWith("e1")

    // Toggling visibility without a new event must not re-record e1.
    act(() => setVisibility("hidden"))
    act(() => setVisibility("visible"))
    expect(recordVisit).toHaveBeenCalledTimes(1)

    // A new event advances the cursor once.
    rerender({ id: "e2" })
    expect(recordVisit).toHaveBeenCalledTimes(2)
    expect(recordVisit).toHaveBeenLastCalledWith("e2")
  })
})
