import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { useNewCommentsIndicator } from "~/react/features/postShow/hooks/useNewCommentsIndicator"

const mockedFetch = vi.mocked(apiFetch)

beforeEach(() => {
  vi.useFakeTimers()
  mockedFetch.mockResolvedValue(undefined)
})
afterEach(() => {
  vi.useRealTimers()
  mockedFetch.mockReset()
  vi.restoreAllMocks()
})

describe("useNewCommentsIndicator", () => {
  test("notifyNewComment sets hasNew; dismiss clears it", () => {
    const { result } = renderHook(() => useNewCommentsIndicator({ workspaceId: null }))
    expect(result.current.hasNew).toBe(false)
    act(() => result.current.notifyNewComment())
    expect(result.current.hasNew).toBe(true)
    act(() => result.current.dismiss())
    expect(result.current.hasNew).toBe(false)
  })

  test("scrollToNew scrolls a tracked element into view and clears the pill", () => {
    const el = document.createElement("div")
    document.body.appendChild(el)
    const scrollIntoView = vi.spyOn(el, "scrollIntoView").mockImplementation(() => {})

    const { result } = renderHook(() => useNewCommentsIndicator({ workspaceId: null }))
    act(() => result.current.notifyNewComment(el))
    expect(result.current.hasNew).toBe(true)

    act(() => result.current.scrollToNew())
    expect(scrollIntoView).toHaveBeenCalled()
    expect(result.current.hasNew).toBe(false)
    el.remove()
  })

  test("debounces the visit catch-up to one workspace POST per burst (no last_event_id)", () => {
    const { result } = renderHook(() => useNewCommentsIndicator({ workspaceId: "ws-1" }))

    act(() => {
      result.current.notifyNewComment()
      result.current.notifyNewComment()
      result.current.notifyNewComment()
    })
    expect(mockedFetch).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(1000))
    expect(mockedFetch).toHaveBeenCalledTimes(1)
    expect(mockedFetch).toHaveBeenCalledWith("/api/workspaces/ws-1/visits", {
      method: "POST",
      body: JSON.stringify({ last_event_id: null }),
    })
  })

  test("does not record a visit when workspaceId is null", () => {
    const { result } = renderHook(() => useNewCommentsIndicator({ workspaceId: null }))
    act(() => result.current.notifyNewComment())
    act(() => vi.advanceTimersByTime(2000))
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  test("recordVisit posts the visit immediately (no debounce)", () => {
    const { result } = renderHook(() => useNewCommentsIndicator({ workspaceId: "ws-1" }))
    act(() => result.current.recordVisit())
    expect(mockedFetch).toHaveBeenCalledTimes(1)
    expect(mockedFetch).toHaveBeenCalledWith("/api/workspaces/ws-1/visits", {
      method: "POST",
      body: JSON.stringify({ last_event_id: null }),
    })
  })

  test("recordVisit is a no-op when workspaceId is null", () => {
    const { result } = renderHook(() => useNewCommentsIndicator({ workspaceId: null }))
    act(() => result.current.recordVisit())
    expect(mockedFetch).not.toHaveBeenCalled()
  })
})
