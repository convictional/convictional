import { act, cleanup, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useEnvelope } from "~/react/composites/emailComposer/hooks/useEnvelope"

const apiFetchMock = vi.fn()

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: (url: string, options?: RequestInit) => apiFetchMock(url, options),
}))

const PATCH_URL = "/api/email_threads/T/draft"

const initialEnvelope = {
  to: [],
  cc: [],
  bcc: [],
  subject: "",
  inReplyToId: null,
}

describe("useEnvelope", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue(undefined)
    // The unmount cleanup effect calls window.fetch with the relative PATCH_URL
    // when pendingRef still holds writes — jsdom can't parse a bare path. Stub
    // globalThis.fetch as a no-op so unmount-flush doesn't trip an unhandled
    // rejection. Tests that need to assert the keepalive call install their
    // own per-test spy on top.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  })

  afterEach(() => {
    // Unmount rendered hooks while the fetch stub from beforeEach is still
    // installed. The global afterEach(cleanup) in vitest.setup.ts runs after
    // this hook (inner afterEach first), by which point unstubAllGlobals has
    // already restored the real fetch — and undici rejects the relative
    // PATCH URL the useEffect cleanup tries to flush.
    cleanup()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("marks unsaved on change and debounces a PATCH containing only the dirty field", async () => {
    const { result } = renderHook(() =>
      useEnvelope({ patchUrl: PATCH_URL, initialEnvelope })
    )

    act(() => result.current.setSubject("Hello"))
    expect(result.current.unsavedChanges).toBe(true)
    expect(result.current.dirty.subject).toBe(true)
    expect(result.current.dirty.to).toBe(false)
    expect(apiFetchMock).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(500)
      await Promise.resolve()
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    const [url, options] = apiFetchMock.mock.calls[0]
    expect(url).toBe(PATCH_URL)
    expect(options.method).toBe("PATCH")
    const body = JSON.parse(options.body)
    expect(body).toEqual({ subject: "Hello" })
    expect(result.current.unsavedChanges).toBe(false)
    expect(result.current.dirty.subject).toBe(false)
  })

  it("coalesces multiple writes into one PATCH with all dirty fields", async () => {
    const { result } = renderHook(() =>
      useEnvelope({ patchUrl: PATCH_URL, initialEnvelope })
    )

    act(() => {
      result.current.setSubject("Hi")
      result.current.setTo(["a@example.com"])
    })

    await act(async () => {
      vi.advanceTimersByTime(500)
      await Promise.resolve()
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    const body = JSON.parse(apiFetchMock.mock.calls[0][1].body)
    expect(body).toEqual({ subject: "Hi", to: ["a@example.com"] })
  })

  it("applyRemote* overwrites clean fields and drops dirty ones", () => {
    const { result } = renderHook(() =>
      useEnvelope({ patchUrl: PATCH_URL, initialEnvelope })
    )

    act(() => result.current.setSubject("local"))
    expect(result.current.subject).toBe("local")

    let appliedToClean = false
    let appliedToDirty = false
    act(() => {
      appliedToClean = result.current.applyRemoteTo(["x@example.com"])
      appliedToDirty = result.current.applyRemoteSubject("remote")
    })

    expect(appliedToClean).toBe(true)
    expect(appliedToDirty).toBe(false)
    expect(result.current.to).toEqual(["x@example.com"])
    expect(result.current.subject).toBe("local")
  })

  it("applyRemoteCc reveals the Cc input when value is non-empty", () => {
    const { result } = renderHook(() =>
      useEnvelope({ patchUrl: PATCH_URL, initialEnvelope })
    )

    expect(result.current.showCc).toBe(false)
    act(() => {
      result.current.applyRemoteCc(["partner@example.com"])
    })
    expect(result.current.showCc).toBe(true)
    expect(result.current.cc).toEqual(["partner@example.com"])
  })

  it("re-merges a failed PATCH payload into the next flush so writes aren't lost", async () => {
    apiFetchMock.mockReset()
    apiFetchMock.mockRejectedValueOnce(new Error("network"))
    apiFetchMock.mockResolvedValue(undefined)

    const { result } = renderHook(() =>
      useEnvelope({ patchUrl: PATCH_URL, initialEnvelope })
    )

    act(() => result.current.setSubject("a"))

    // Fire the debounce → PATCH #1 starts and suspends at apiFetch with
    // inFlightRef = true. Before the rejection drains, synchronously queue a
    // setTo so the new write lands in pendingRef without scheduling its own
    // timer. The catch should then re-merge {subject: "a"} alongside it.
    await act(async () => {
      vi.advanceTimersByTime(500)
      result.current.setTo(["x@example.com"])
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect(JSON.parse(apiFetchMock.mock.calls[0][1].body)).toEqual({ subject: "a" })
    expect(result.current.unsavedChanges).toBe(true)
    expect(result.current.dirty.subject).toBe(true)
    expect(result.current.dirty.to).toBe(true)

    // The finally scheduled a retry timer because writes arrived during the
    // flight. Advance it → PATCH #2 carries the re-merged subject plus the to.
    await act(async () => {
      vi.advanceTimersByTime(500)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    expect(JSON.parse(apiFetchMock.mock.calls[1][1].body)).toEqual({
      subject: "a",
      to: ["x@example.com"],
    })
    expect(result.current.unsavedChanges).toBe(false)
    expect(result.current.dirty).toEqual({ to: false, cc: false, bcc: false, subject: false })
  })

  it("flushes pending writes via keepalive fetch on unmount", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 204 })
    )

    const { result, unmount } = renderHook(() =>
      useEnvelope({ patchUrl: PATCH_URL, initialEnvelope })
    )

    act(() => result.current.setSubject("unsaved"))
    // Unmount before the debounce timer fires.
    unmount()

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [url, options] = fetchSpy.mock.calls[0]
    expect(url).toBe(PATCH_URL)
    expect(options?.method).toBe("PATCH")
    expect(options?.keepalive).toBe(true)
    const body = JSON.parse(options?.body as string)
    expect(body).toEqual({ subject: "unsaved" })

    fetchSpy.mockRestore()
  })

  // Sets up the in-flight-PATCH scenario: starts a subject PATCH, queues a
  // setTo() while the PATCH is suspended, then resolves the PATCH. Returns with:
  // dirty.subject=false (just saved), dirty.to=true, pendingRef.to set.
  async function queueToDuringSubjectPatch() {
    apiFetchMock.mockReset()
    let resolveFetch: ((value?: unknown) => void) | null = null
    apiFetchMock.mockImplementationOnce(
      () => new Promise(resolve => { resolveFetch = resolve })
    )
    apiFetchMock.mockResolvedValue(undefined)

    const { result, unmount } = renderHook(() =>
      useEnvelope({ patchUrl: PATCH_URL, initialEnvelope })
    )

    act(() => result.current.setSubject("a"))

    await act(async () => {
      vi.advanceTimersByTime(500)
      result.current.setTo(["x@example.com"])
      await Promise.resolve()
    })

    await act(async () => {
      resolveFetch?.(undefined)
      await Promise.resolve()
      await Promise.resolve()
    })

    return { result, unmount }
  }

  it("clears dirty only for fields included in the PATCH payload", async () => {
    const { result, unmount } = await queueToDuringSubjectPatch()

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect(JSON.parse(apiFetchMock.mock.calls[0][1].body)).toEqual({ subject: "a" })
    expect(result.current.dirty.subject).toBe(false)
    expect(result.current.dirty.to).toBe(true)
    expect(result.current.unsavedChanges).toBe(true)

    await act(async () => {
      vi.advanceTimersByTime(500)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    expect(JSON.parse(apiFetchMock.mock.calls[1][1].body)).toEqual({ to: ["x@example.com"] })
    expect(result.current.dirty.to).toBe(false)
    expect(result.current.unsavedChanges).toBe(false)

    unmount()
  })

  it("applyRemoteTo drops the inbound value when pendingRef has a pending To even after dirty was reset", async () => {
    const { result, unmount } = await queueToDuringSubjectPatch()

    // Reset dirty to simulate the post-PATCH dirty-clear state where dirty.to is
    // false but pendingRef.to is still set — the pendingRef gate must drop the inbound.
    act(() => result.current.resetDirty())
    expect(result.current.dirty.to).toBe(false)  // sanity: dirty really is cleared

    let applied = true
    act(() => {
      applied = result.current.applyRemoteTo(["server-side@example.com"])
    })

    expect(applied).toBe(false)
    expect(result.current.to).toEqual(["x@example.com"])

    unmount()
  })

  it("setSubject dispatches the draft-subject-changed event for the Alpine thread header", () => {
    const listener = vi.fn()
    window.addEventListener("draft-subject-changed", listener as EventListener)

    const { result } = renderHook(() =>
      useEnvelope({ patchUrl: PATCH_URL, initialEnvelope })
    )
    act(() => result.current.setSubject("New subject"))

    expect(listener).toHaveBeenCalled()
    const event = listener.mock.calls[0][0] as CustomEvent
    expect(event.detail.subject).toBe("New subject")

    window.removeEventListener("draft-subject-changed", listener as EventListener)
  })
})
