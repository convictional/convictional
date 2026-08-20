import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { useAutoMarkRead } from "~/react/shared/hooks/useAutoMarkRead"

const mockedFetch = vi.mocked(apiFetch)

interface FakeObserver {
  cb: IntersectionObserverCallback
  connected: boolean
}
const observers: FakeObserver[] = []

function fireIntersect(visible: boolean): void {
  for (const o of observers) {
    if (o.connected) o.cb([{ isIntersecting: visible } as IntersectionObserverEntry], {} as IntersectionObserver)
  }
}

function makeRef(): { current: HTMLElement } {
  return { current: document.createElement("div") }
}

beforeEach(() => {
  observers.length = 0
  vi.useFakeTimers()
  vi.stubGlobal(
    "IntersectionObserver",
    vi.fn(function (cb: IntersectionObserverCallback) {
      const observer: FakeObserver = { cb, connected: true }
      observers.push(observer)
      return {
        observe: vi.fn(),
        disconnect: vi.fn(() => {
          observer.connected = false
        }),
        unobserve: vi.fn(),
        takeRecords: vi.fn(),
      }
    })
  )
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  mockedFetch.mockReset()
})

describe("useAutoMarkRead", () => {
  test("POSTs once after the delay, dispatches the event, and calls onMarkedRead", async () => {
    mockedFetch.mockResolvedValue(undefined)
    const onMarkedRead = vi.fn()
    const listener = vi.fn()
    window.addEventListener("thread-marked-read", listener)
    const ref = makeRef()

    renderHook(() => useAutoMarkRead({ ref, enabled: true, url: "/api/x/mark_read", onMarkedRead, delayMs: 1000 }))

    act(() => fireIntersect(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(mockedFetch).toHaveBeenCalledWith("/api/x/mark_read", { method: "POST" })
    expect(mockedFetch).toHaveBeenCalledTimes(1)
    expect(onMarkedRead).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledTimes(1)
    window.removeEventListener("thread-marked-read", listener)
  })

  test("does not fire if visibility is lost before the delay", async () => {
    mockedFetch.mockResolvedValue(undefined)
    const ref = makeRef()
    renderHook(() => useAutoMarkRead({ ref, enabled: true, url: "/api/x/mark_read", onMarkedRead: vi.fn() }))

    act(() => fireIntersect(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    act(() => fireIntersect(false))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  test("retries on the next re-entry after a failed POST", async () => {
    mockedFetch.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(undefined)
    const ref = makeRef()
    renderHook(() => useAutoMarkRead({ ref, enabled: true, url: "/api/x/mark_read", onMarkedRead: vi.fn(), delayMs: 0 }))

    act(() => fireIntersect(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(mockedFetch).toHaveBeenCalledTimes(1)

    act(() => fireIntersect(false))
    act(() => fireIntersect(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(mockedFetch).toHaveBeenCalledTimes(2)
  })

  test("enabled:false never observes or fires", () => {
    const ref = makeRef()
    renderHook(() => useAutoMarkRead({ ref, enabled: false, url: "/api/x/mark_read", onMarkedRead: vi.fn() }))
    expect(globalThis.IntersectionObserver).not.toHaveBeenCalled()
  })
})
