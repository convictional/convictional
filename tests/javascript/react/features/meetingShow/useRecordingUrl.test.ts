import { renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { ApiError, apiFetch } from "~/react/shared/apiFetch"

import { useRecordingUrl } from "~/react/features/meetingShow/hooks/useRecordingUrl"

const mockedFetch = vi.mocked(apiFetch)
const videoRef = { current: null }

beforeEach(() => {
  mockedFetch.mockReset()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("useRecordingUrl", () => {
  test("resolves the signed url and is not missing", async () => {
    mockedFetch.mockResolvedValueOnce({ url: "https://signed/recording.mp4" })

    const { result } = renderHook(() => useRecordingUrl("meeting-1", true, videoRef))

    await waitFor(() => expect(result.current.url).toBe("https://signed/recording.mp4"))
    expect(result.current.missing).toBe(false)
  })

  test("flags missing (not a perpetual spinner) when the recording 404s", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError(404, { detail: "Recording not found" }))

    const { result } = renderHook(() => useRecordingUrl("meeting-1", true, videoRef))

    await waitFor(() => expect(result.current.missing).toBe(true))
    expect(result.current.url).toBeNull()
  })

  test("does not fetch when the meeting has no recording", () => {
    renderHook(() => useRecordingUrl("meeting-1", false, videoRef))

    expect(mockedFetch).not.toHaveBeenCalled()
  })

  test("on visibility change while paused, swaps the source and reloads the element", async () => {
    const videoEl = document.createElement("video")
    const source = document.createElement("source")
    videoEl.appendChild(source)
    // jsdom doesn't implement load(); stub it so we can assert it ran. The
    // element is paused by default, which is the refresh precondition.
    const loadSpy = vi.spyOn(videoEl, "load").mockImplementation(() => {})
    const ref = { current: videoEl }

    mockedFetch.mockResolvedValueOnce({ url: "https://signed/a.mp4" })
    const { result } = renderHook(() => useRecordingUrl("meeting-1", true, ref))
    await waitFor(() => expect(result.current.url).toBe("https://signed/a.mp4"))

    // A genuinely different URL must take effect: setting React state alone
    // would leave the playing <source> untouched until load() is called.
    mockedFetch.mockResolvedValueOnce({ url: "https://signed/b.mp4" })
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" })
    document.dispatchEvent(new Event("visibilitychange"))

    await waitFor(() => expect(source.src).toContain("b.mp4"))
    expect(loadSpy).toHaveBeenCalled()
  })
})
