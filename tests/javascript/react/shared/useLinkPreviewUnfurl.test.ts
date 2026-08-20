import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { useLinkPreviewUnfurl } from "~/react/shared/hooks/useLinkPreviewUnfurl"

const mockedFetch = vi.mocked(apiFetch)

const PREVIEW = {
  url: "https://example.com",
  type: "link",
  title: "Example",
  description: "An example",
  image_url: null,
  site_name: null,
  domain: "example.com",
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  mockedFetch.mockReset()
})

async function flushDebounce() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(500)
  })
}

describe("useLinkPreviewUnfurl", () => {
  test("fetches the first URL after the debounce and returns the preview", async () => {
    mockedFetch.mockResolvedValue({ link_preview: PREVIEW })
    const { result, rerender } = renderHook(({ content }) => useLinkPreviewUnfurl(content), {
      initialProps: { content: "" },
    })

    rerender({ content: "check out https://example.com" })
    expect(mockedFetch).not.toHaveBeenCalled()
    await flushDebounce()

    expect(mockedFetch).toHaveBeenCalledTimes(1)
    const [url, init] = mockedFetch.mock.calls[0]
    expect(url).toBe("/api/link_previews/unfurl")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ url: "https://example.com" })
    expect(result.current.composePreview).toEqual(PREVIEW)
    expect(result.current.dismissed).toBe(false)

    // Content edits that keep the same first URL don't re-fetch.
    rerender({ content: "check out https://example.com please" })
    await flushDebounce()
    expect(mockedFetch).toHaveBeenCalledTimes(1)
  })

  test("passes a URL with balanced parentheses verbatim to the unfurl API", async () => {
    mockedFetch.mockResolvedValue({ link_preview: PREVIEW })
    const parenUrl = "https://en.wikipedia.org/wiki/Scheme_(programming_language)"
    const { rerender } = renderHook(({ content }) => useLinkPreviewUnfurl(content), {
      initialProps: { content: "" },
    })

    rerender({ content: `read ${parenUrl}` })
    await flushDebounce()

    expect(mockedFetch).toHaveBeenCalledTimes(1)
    const [, init] = mockedFetch.mock.calls[0]
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ url: parenUrl })
  })

  test("ignores image markdown (no fetch for a GIF-only body)", async () => {
    const { result, rerender } = renderHook(({ content }) => useLinkPreviewUnfurl(content), {
      initialProps: { content: "" },
    })

    rerender({ content: "![cat](https://media.example.com/cat.gif)" })
    await flushDebounce()

    expect(mockedFetch).not.toHaveBeenCalled()
    expect(result.current.composePreview).toBeNull()
  })

  test("returns null when the unfurl yields no preview", async () => {
    mockedFetch.mockResolvedValue({ link_preview: null })
    const { result, rerender } = renderHook(({ content }) => useLinkPreviewUnfurl(content), {
      initialProps: { content: "" },
    })

    rerender({ content: "https://example.com" })
    await flushDebounce()

    expect(mockedFetch).toHaveBeenCalledTimes(1)
    expect(result.current.composePreview).toBeNull()
  })

  test("changing the URL hides the previous preview while the new one unfurls; same-URL re-typing re-shows instantly", async () => {
    mockedFetch.mockResolvedValue({ link_preview: PREVIEW })
    const { result, rerender } = renderHook(({ content }) => useLinkPreviewUnfurl(content), {
      initialProps: { content: "https://example.com" },
    })
    await flushDebounce()
    expect(result.current.composePreview).toEqual(PREVIEW)

    // New URL: the cached preview is for the old URL — it must not flash
    // under the new one while the fetch is pending.
    const other = { ...PREVIEW, url: "https://other.com", domain: "other.com" }
    mockedFetch.mockResolvedValue({ link_preview: other })
    rerender({ content: "https://other.com" })
    expect(result.current.composePreview).toBeNull()
    await flushDebounce()
    expect(result.current.composePreview).toEqual(other)

    // Deleting and re-typing the same URL re-shows the cached preview
    // immediately (no blank flash while the re-fetch refreshes it).
    rerender({ content: "" })
    rerender({ content: "https://other.com" })
    expect(result.current.composePreview).toEqual(other)
  })

  test("a stale in-flight fetch is aborted when the URL changes; the new URL's preview wins", async () => {
    const pending: { url: string; resolve: (lp: typeof PREVIEW | null) => void }[] = []
    mockedFetch.mockImplementation((_url, init) => {
      const requestInit = init as RequestInit
      const { url } = JSON.parse(requestInit.body as string) as { url: string }
      return new Promise((resolve, reject) => {
        requestInit.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))
        pending.push({ url, resolve: lp => resolve({ link_preview: lp }) })
      })
    })

    const { result, rerender } = renderHook(({ content }) => useLinkPreviewUnfurl(content), {
      initialProps: { content: "https://slow.example.com" },
    })
    await flushDebounce()
    expect(pending.map(p => p.url)).toEqual(["https://slow.example.com"])

    // First fetch still in flight; the user replaces the URL.
    rerender({ content: "https://fast.example.com" })
    await flushDebounce()
    expect(pending.map(p => p.url)).toEqual(["https://slow.example.com", "https://fast.example.com"])

    const fastPreview = { ...PREVIEW, url: "https://fast.example.com", title: "Fast" }
    await act(async () => {
      pending[1].resolve(fastPreview)
      // The slow response landing late must not clobber the fast one — its
      // controller was aborted, so this resolve is a no-op.
      pending[0].resolve({ ...PREVIEW, title: "Slow" })
    })

    expect(result.current.composePreview).toEqual(fastPreview)
  })

  test("isUrlDismissed judges fresh content against the dismissed URL", async () => {
    mockedFetch.mockResolvedValue({ link_preview: PREVIEW })
    const { result } = renderHook(({ content }) => useLinkPreviewUnfurl(content), {
      initialProps: { content: "https://example.com" },
    })
    await flushDebounce()

    expect(result.current.isUrlDismissed("see https://example.com")).toBe(false)
    act(() => result.current.dismissComposePreview())
    expect(result.current.isUrlDismissed("see https://example.com")).toBe(true)
    expect(result.current.isUrlDismissed("see https://other.com")).toBe(false)
    expect(result.current.isUrlDismissed("no url at all")).toBe(false)
  })

  test("dismissal is per-URL: the same URL stays dismissed, a new URL re-enables", async () => {
    mockedFetch.mockResolvedValue({ link_preview: PREVIEW })
    const { result, rerender } = renderHook(({ content }) => useLinkPreviewUnfurl(content), {
      initialProps: { content: "https://example.com" },
    })
    await flushDebounce()
    expect(result.current.composePreview).toEqual(PREVIEW)

    act(() => result.current.dismissComposePreview())
    expect(result.current.composePreview).toBeNull()
    expect(result.current.dismissed).toBe(true)

    // Same URL after more typing: still dismissed.
    rerender({ content: "https://example.com and more" })
    await flushDebounce()
    expect(result.current.composePreview).toBeNull()
    expect(result.current.dismissed).toBe(true)

    // A different first URL re-enables the preview.
    const other = { ...PREVIEW, url: "https://other.com", domain: "other.com" }
    mockedFetch.mockResolvedValue({ link_preview: other })
    rerender({ content: "https://other.com" })
    await flushDebounce()
    expect(result.current.composePreview).toEqual(other)
    expect(result.current.dismissed).toBe(false)
  })
})
