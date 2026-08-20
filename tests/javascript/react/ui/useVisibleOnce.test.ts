import { act, renderHook } from "@testing-library/react"
import { StrictMode } from "react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { useVisibleOnce } from "~/react/ui/hooks/useVisibleOnce"

// Manual IntersectionObserver stub modelling real disconnect semantics: a
// disconnected observer never receives further callbacks, so fireIntersect
// skips it. This is what makes the StrictMode / re-arm cases meaningful.
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
  vi.restoreAllMocks()
})

describe("useVisibleOnce", () => {
  test("fires once after the element is continuously visible for delayMs", () => {
    const onVisible = vi.fn()
    const ref = makeRef()
    renderHook(() => useVisibleOnce({ ref, onVisible, delayMs: 1000 }))

    act(() => fireIntersect(true))
    expect(onVisible).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1000))
    expect(onVisible).toHaveBeenCalledTimes(1)

    // Staying visible never refires.
    act(() => fireIntersect(true))
    act(() => vi.advanceTimersByTime(2000))
    expect(onVisible).toHaveBeenCalledTimes(1)
  })

  test("cancels the pending fire if the element leaves before delayMs", () => {
    const onVisible = vi.fn()
    const ref = makeRef()
    renderHook(() => useVisibleOnce({ ref, onVisible, delayMs: 1000 }))

    act(() => fireIntersect(true))
    act(() => vi.advanceTimersByTime(500))
    act(() => fireIntersect(false))
    act(() => vi.advanceTimersByTime(2000))
    expect(onVisible).not.toHaveBeenCalled()
  })

  test("re-entry after leaving early restarts the timer", () => {
    const onVisible = vi.fn()
    const ref = makeRef()
    renderHook(() => useVisibleOnce({ ref, onVisible, delayMs: 1000 }))

    act(() => fireIntersect(true))
    act(() => vi.advanceTimersByTime(500))
    act(() => fireIntersect(false))
    act(() => fireIntersect(true))
    act(() => vi.advanceTimersByTime(1000))
    expect(onVisible).toHaveBeenCalledTimes(1)
  })

  test("re-arms when a dep changes", () => {
    const onVisible = vi.fn()
    const ref = makeRef()
    const { rerender } = renderHook(({ id }) => useVisibleOnce({ ref, onVisible }, [id]), {
      initialProps: { id: "a" },
    })

    act(() => {
      fireIntersect(true)
      vi.advanceTimersByTime(0)
    })
    expect(onVisible).toHaveBeenCalledTimes(1)

    rerender({ id: "b" })
    act(() => {
      fireIntersect(true)
      vi.advanceTimersByTime(0)
    })
    expect(onVisible).toHaveBeenCalledTimes(2)
  })

  test("does not re-create the observer when only onVisible identity changes", () => {
    const ref = makeRef()
    const { rerender } = renderHook(({ cb }) => useVisibleOnce({ ref, onVisible: cb }), {
      initialProps: { cb: vi.fn() },
    })
    const created = vi.mocked(globalThis.IntersectionObserver).mock.calls.length
    rerender({ cb: vi.fn() })
    expect(vi.mocked(globalThis.IntersectionObserver).mock.calls.length).toBe(created)
  })

  test("calls the latest onVisible even though identity changed", () => {
    const first = vi.fn()
    const second = vi.fn()
    const ref = makeRef()
    const { rerender } = renderHook(({ cb }) => useVisibleOnce({ ref, onVisible: cb }), {
      initialProps: { cb: first },
    })
    rerender({ cb: second })
    act(() => {
      fireIntersect(true)
      vi.advanceTimersByTime(0)
    })
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
  })

  test("enabled:false and a null ref are no-ops", () => {
    const onVisible = vi.fn()
    renderHook(() => useVisibleOnce({ ref: makeRef(), onVisible, enabled: false }))
    expect(globalThis.IntersectionObserver).not.toHaveBeenCalled()

    renderHook(() => useVisibleOnce({ ref: { current: null }, onVisible }))
    expect(globalThis.IntersectionObserver).not.toHaveBeenCalled()
    act(() => fireIntersect(true))
    expect(onVisible).not.toHaveBeenCalled()
  })

  test("a rejected async onVisible stays armed and retries on re-entry", async () => {
    const onVisible = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(undefined)
    const ref = makeRef()
    renderHook(() => useVisibleOnce({ ref, onVisible, delayMs: 0 }))

    act(() => fireIntersect(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(onVisible).toHaveBeenCalledTimes(1)

    // Failure left it armed: a re-entry retries.
    act(() => fireIntersect(false))
    act(() => fireIntersect(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(onVisible).toHaveBeenCalledTimes(2)
  })

  test("a resolved async onVisible disconnects and does not retry", async () => {
    const onVisible = vi.fn().mockResolvedValue(undefined)
    const ref = makeRef()
    renderHook(() => useVisibleOnce({ ref, onVisible, delayMs: 0 }))

    act(() => fireIntersect(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    act(() => fireIntersect(false))
    act(() => fireIntersect(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(onVisible).toHaveBeenCalledTimes(1)
  })

  test("fires exactly once under StrictMode mount/unmount", () => {
    const onVisible = vi.fn()
    const ref = makeRef()
    renderHook(() => useVisibleOnce({ ref, onVisible, delayMs: 1000 }), { wrapper: StrictMode })

    act(() => fireIntersect(true))
    act(() => vi.advanceTimersByTime(1000))
    expect(onVisible).toHaveBeenCalledTimes(1)
  })
})
