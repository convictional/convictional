import { renderHook } from "@testing-library/react"
import { useRef } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useScrollToDraft } from "~/react/features/emailThreadShow/hooks/useScrollToDraft"

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("useScrollToDraft", () => {
  it("scrolls to the composer with header offset baked in and smooth behavior", () => {
    const scrollSpy = vi.spyOn(window, "scrollTo").mockImplementation(() => {})

    const target = document.createElement("div")
    Object.defineProperty(target, "getBoundingClientRect", {
      value: () => ({ top: 600, left: 0, right: 0, bottom: 700, height: 100, width: 0, x: 0, y: 600, toJSON: () => "" }),
    })
    document.body.appendChild(target)
    Object.defineProperty(window, "scrollY", { value: 0, configurable: true })

    renderHook(() => {
      const ref = useRef<HTMLElement | null>(target)
      useScrollToDraft({ composerRef: ref, scrollKey: "draft-abc" })
    })
    vi.advanceTimersByTime(160)

    expect(scrollSpy).toHaveBeenCalledTimes(1)
    expect(scrollSpy).toHaveBeenCalledWith({ top: 450, behavior: "smooth" })

    document.body.removeChild(target)
  })

  it("does nothing when scrollKey is null", () => {
    const scrollSpy = vi.spyOn(window, "scrollTo").mockImplementation(() => {})

    const target = document.createElement("div")
    Object.defineProperty(target, "getBoundingClientRect", {
      value: () => ({ top: 600, left: 0, right: 0, bottom: 700, height: 100, width: 0, x: 0, y: 600, toJSON: () => "" }),
    })
    document.body.appendChild(target)

    renderHook(() => {
      const ref = useRef<HTMLElement | null>(target)
      useScrollToDraft({ composerRef: ref, scrollKey: null })
    })
    vi.advanceTimersByTime(160)

    expect(scrollSpy).not.toHaveBeenCalled()

    document.body.removeChild(target)
  })

  it("re-fires on draft-id transition (covers 409 conflict-replace path)", () => {
    const scrollSpy = vi.spyOn(window, "scrollTo").mockImplementation(() => {})

    const target = document.createElement("div")
    Object.defineProperty(target, "getBoundingClientRect", {
      value: () => ({ top: 600, left: 0, right: 0, bottom: 700, height: 100, width: 0, x: 0, y: 600, toJSON: () => "" }),
    })
    document.body.appendChild(target)
    Object.defineProperty(window, "scrollY", { value: 0, configurable: true })

    const { rerender } = renderHook(
      ({ scrollKey }: { scrollKey: string | null }) => {
        const ref = useRef<HTMLElement | null>(target)
        useScrollToDraft({ composerRef: ref, scrollKey })
      },
      { initialProps: { scrollKey: "draft-A" as string | null } }
    )
    vi.advanceTimersByTime(160)

    rerender({ scrollKey: "draft-B" })
    vi.advanceTimersByTime(160)

    expect(scrollSpy).toHaveBeenCalledTimes(2)

    document.body.removeChild(target)
  })
})
