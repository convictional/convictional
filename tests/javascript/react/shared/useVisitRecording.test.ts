import { renderHook } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { useVisitRecording, useWorkspaceVisitRecording } from "~/react/shared/hooks/useVisitRecording"

const mockedFetch = vi.mocked(apiFetch)

afterEach(() => {
  mockedFetch.mockReset()
})

describe("useVisitRecording", () => {
  test("posts the event id to the given endpoint", () => {
    mockedFetch.mockResolvedValue(undefined)
    const { result } = renderHook(() => useVisitRecording("/api/workspaces/w1/visits"))
    result.current("evt-1")
    expect(mockedFetch).toHaveBeenCalledWith("/api/workspaces/w1/visits", {
      method: "POST",
      body: JSON.stringify({ last_event_id: "evt-1" }),
    })
  })

  test("an omitted event id sends null", () => {
    mockedFetch.mockResolvedValue(undefined)
    const { result } = renderHook(() => useVisitRecording("/api/workspaces/w1/visits"))
    result.current()
    expect(mockedFetch).toHaveBeenCalledWith("/api/workspaces/w1/visits", {
      method: "POST",
      body: JSON.stringify({ last_event_id: null }),
    })
  })

  test("swallows errors and a later call still fires", async () => {
    mockedFetch.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(undefined)
    const { result } = renderHook(() => useVisitRecording("/api/workspaces/w1/visits"))
    expect(() => result.current()).not.toThrow()
    await Promise.resolve()
    result.current("evt-2")
    expect(mockedFetch).toHaveBeenCalledTimes(2)
  })

  test("no-ops when the url is null (resource not loaded yet)", () => {
    mockedFetch.mockResolvedValue(undefined)
    const { result } = renderHook(() => useVisitRecording(null))
    result.current("evt-1")
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  test("callback identity is stable across renders with an unchanged url", () => {
    const { result, rerender } = renderHook(({ url }) => useVisitRecording(url), {
      initialProps: { url: "/api/workspaces/w1/visits" },
    })
    const first = result.current
    rerender({ url: "/api/workspaces/w1/visits" })
    expect(result.current).toBe(first)
    rerender({ url: "/api/workspaces/w2/visits" })
    expect(result.current).not.toBe(first)
  })
})

describe("useWorkspaceVisitRecording", () => {
  test("posts to the workspace endpoint for the given id", () => {
    mockedFetch.mockResolvedValue(undefined)
    const { result } = renderHook(() => useWorkspaceVisitRecording("w1"))
    result.current()
    expect(mockedFetch).toHaveBeenCalledWith("/api/workspaces/w1/visits", {
      method: "POST",
      body: JSON.stringify({ last_event_id: null }),
    })
  })

  test("no-ops when the workspace id is null (not loaded yet)", () => {
    mockedFetch.mockResolvedValue(undefined)
    const { result } = renderHook(() => useWorkspaceVisitRecording(null))
    result.current()
    expect(mockedFetch).not.toHaveBeenCalled()
  })
})
