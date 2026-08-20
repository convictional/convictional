import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)

vi.mock("~/shared/csrf", () => ({
  getCSRFToken: () => "csrf-token",
  isCSRFFailure: () => false,
  showSessionChangedFlash: () => {},
}))

import { useCommentSubmit } from "~/react/features/emailThreadShow/hooks/useCommentSubmit"

const COMMENT = {
  id: "c1",
  content: "Hello",
  user: { id: "u1", display_name: "Alice", picture: null },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  reactions: {},
  link_preview: null,
  attachments: [],
}

function jsonResponse(body: unknown, status = 201): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })
}

beforeEach(() => {
  fetchMock.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("useCommentSubmit", () => {
  it("POSTs the caller's claim id, content, unfurl_links, and CSRF header to the thread endpoint", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(COMMENT))
    const { result } = renderHook(() => useCommentSubmit({ threadId: "T" }))

    let returned: unknown
    await act(async () => {
      returned = await result.current.send("  Hello  ", "claim-1")
    })

    expect(returned).toEqual(COMMENT)
    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("/api/email_threads/T/comments")
    expect(init.method).toBe("POST")
    expect((init.headers as Record<string, string>)["X-CSRFToken"]).toBe("csrf-token")
    // Only trailing whitespace is stripped (via trimEnd), so leading whitespace —
    // the NBSP the serializer emits to preserve indentation — survives to the API.
    // The composer's claim id is passed straight through.
    expect(JSON.parse(init.body as string)).toEqual({
      content: "  Hello",
      attachment_claim_id: "claim-1",
      unfurl_links: true,
    })
  })

  it("passes unfurl_links=false when the composer's preview was dismissed", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(COMMENT))
    const { result } = renderHook(() => useCommentSubmit({ threadId: "T" }))
    await act(async () => {
      await result.current.send("Hello", "claim-1", false)
    })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).unfurl_links).toBe(false)
  })

  it("includes reply_to_id only when quote-replying", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(COMMENT)).mockResolvedValueOnce(jsonResponse(COMMENT))
    const { result } = renderHook(() => useCommentSubmit({ threadId: "T" }))

    await act(async () => {
      await result.current.send("A reply", "claim-1", true, "target-c")
    })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).reply_to_id).toBe("target-c")

    // A plain comment omits the field entirely rather than sending null.
    await act(async () => {
      await result.current.send("Plain", "claim-2")
    })
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).not.toHaveProperty("reply_to_id")
  })

  it("returns null without POSTing when markdown is empty or whitespace", async () => {
    const { result } = renderHook(() => useCommentSubmit({ threadId: "T" }))

    let a: unknown, b: unknown
    await act(async () => {
      a = await result.current.send("", "claim-1")
      b = await result.current.send("   \n  ", "claim-1")
    })

    expect(a).toBeNull()
    expect(b).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("calls onSuccess with the created comment after a successful send", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(COMMENT))
    const onSuccess = vi.fn()
    const { result } = renderHook(() => useCommentSubmit({ threadId: "T", onSuccess }))

    await act(async () => {
      await result.current.send("Hello", "claim-1")
    })

    expect(onSuccess).toHaveBeenCalledWith(COMMENT)
    expect(result.current.sending).toBe(false)
  })

  it("returns null on failure without calling onSuccess, then succeeds on a later send", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "boom" }, 500)).mockResolvedValueOnce(jsonResponse(COMMENT))
    const onSuccess = vi.fn()
    const { result } = renderHook(() => useCommentSubmit({ threadId: "T", onSuccess }))

    let failed: unknown
    await act(async () => {
      failed = await result.current.send("Hello", "claim-1")
    })
    expect(failed).toBeNull()
    expect(onSuccess).not.toHaveBeenCalled()

    let succeeded: unknown
    await act(async () => {
      succeeded = await result.current.send("Hello again", "claim-1")
    })
    expect(succeeded).toEqual(COMMENT)
    expect(onSuccess).toHaveBeenCalledWith(COMMENT)
  })

  it("ignores a concurrent send while one is in flight", async () => {
    let resolveFirst: ((value: Response) => void) | null = null
    fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>(r => {
          resolveFirst = r
        })
    )
    const { result } = renderHook(() => useCommentSubmit({ threadId: "T" }))

    let firstSend: Promise<unknown> | null = null
    act(() => {
      firstSend = result.current.send("Hello", "claim-1")
    })
    await waitFor(() => expect(result.current.sending).toBe(true))

    await act(async () => {
      await result.current.send("Hello again", "claim-1")
    })
    expect(fetchMock).toHaveBeenCalledOnce()

    await act(async () => {
      resolveFirst?.(jsonResponse(COMMENT))
      await firstSend
    })
  })
})
