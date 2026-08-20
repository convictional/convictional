import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

describe("apiFetch navigation abort", () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    fetchMock = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          const sig = init?.signal
          if (sig?.aborted) reject(new DOMException("Aborted", "AbortError"))
          else sig?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))
        })
    )
    vi.stubGlobal("fetch", fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("aborts an in-flight request when pagehide fires", async () => {
    const { apiFetch } = await import("~/react/shared/apiFetch")

    const promise = apiFetch("/api/test")

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init).toBeDefined()
    expect(init.signal instanceof AbortSignal).toBe(true)
    expect((init.signal as AbortSignal).aborted).toBe(false)

    window.dispatchEvent(new Event("pagehide"))

    expect((init.signal as AbortSignal).aborted).toBe(true)
    await expect(promise).rejects.toMatchObject({ name: "AbortError" })
  })

  it("combines a caller-supplied signal with the navigation signal", async () => {
    const { apiFetch } = await import("~/react/shared/apiFetch")

    const caller = new AbortController()
    const promise = apiFetch("/api/test", { signal: caller.signal })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init).toBeDefined()
    expect((init.signal as AbortSignal).aborted).toBe(false)

    caller.abort()

    expect((init.signal as AbortSignal).aborted).toBe(true)
    await expect(promise).rejects.toMatchObject({ name: "AbortError" })
  })

  it("uses a fresh navigation controller after pagehide (bfcache restore)", async () => {
    const { apiFetch } = await import("~/react/shared/apiFetch")

    const p1 = apiFetch("/api/a")

    window.dispatchEvent(new Event("pagehide"))

    await expect(p1).rejects.toMatchObject({ name: "AbortError" })

    apiFetch("/api/b")

    const init = fetchMock.mock.calls[1][1] as RequestInit
    expect(init).toBeDefined()
    expect((init.signal as AbortSignal).aborted).toBe(false)
  })
})
