import { renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { ApiError, apiFetch } from "~/react/shared/apiFetch"

import { useTranscript } from "~/react/features/meetingShow/hooks/useTranscript"

const mockedFetch = vi.mocked(apiFetch)

const LINES = [{ line_number: 1, start_time: 0, speaker: "Alice", content: "Hello" }]

beforeEach(() => {
  mockedFetch.mockReset()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("useTranscript", () => {
  test("loads transcript lines", async () => {
    mockedFetch.mockResolvedValueOnce({ lines: LINES })

    const { result } = renderHook(() => useTranscript("meeting-1", false))

    await waitFor(() => expect(result.current.kind).toBe("loaded"))
    expect(result.current).toEqual({ kind: "loaded", lines: LINES })
  })

  test("shows processing when the transcript 404s and work is in flight", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError(404, { detail: "Transcript not found" }))

    const { result } = renderHook(() => useTranscript("meeting-1", true))

    await waitFor(() => expect(result.current.kind).toBe("processing"))
  })

  test("falls back to empty (not a perpetual spinner) when a 404 meeting is not processing", async () => {
    // No Recall bot and no upload job: the transcript-complete callback will
    // never fire, so a spinner here would hang forever. Render the empty state.
    mockedFetch.mockRejectedValueOnce(new ApiError(404, { detail: "Transcript not found" }))

    const { result } = renderHook(() => useTranscript("meeting-1", false))

    await waitFor(() => expect(result.current.kind).toBe("loaded"))
    expect(result.current).toEqual({ kind: "loaded", lines: [] })
  })

  test("re-fetches when processing finishes (false-edge)", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError(404, { detail: "Transcript not found" }))

    const { result, rerender } = renderHook(({ processing }) => useTranscript("meeting-1", processing), {
      initialProps: { processing: true },
    })

    await waitFor(() => expect(result.current.kind).toBe("processing"))

    mockedFetch.mockResolvedValueOnce({ lines: LINES })
    rerender({ processing: false })

    await waitFor(() => expect(result.current).toEqual({ kind: "loaded", lines: LINES }))
    expect(mockedFetch).toHaveBeenCalledTimes(2)
  })
})
