import { cleanup, fireEvent, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/features/meetingShow/hooks/useRecordingUrl", () => ({
  useRecordingUrl: () => ({ url: "https://signed/recording.mp4", missing: false }),
}))

import { VideoPlayer } from "~/react/features/meetingShow/components/VideoPlayer"

function renderPlayer() {
  const onTimeUpdate = vi.fn()
  const videoRef = { current: null as HTMLVideoElement | null }
  const { container } = render(
    <VideoPlayer meetingId="m1" hasRecording videoRef={videoRef} onTimeUpdate={onTimeUpdate} />
  )
  const video = container.querySelector("video")!
  // jsdom's native currentTime setter is unreliable; back it with a plain
  // writable property so the seek is observable and never throws.
  Object.defineProperty(video, "currentTime", { value: 0, writable: true, configurable: true })
  return { onTimeUpdate, video }
}

beforeEach(() => {
  window.location.hash = ""
})

afterEach(() => {
  cleanup()
  window.location.hash = ""
})

describe("VideoPlayer hash seek", () => {
  test("syncs lifted currentTime on loadeddata so a copied link is correct before play", () => {
    window.location.hash = "#timestamp-754"
    const { onTimeUpdate, video } = renderPlayer()

    // No playback — just the loadeddata the browser fires once metadata lands.
    fireEvent.loadedData(video)

    expect(video.currentTime).toBe(754)
    expect(onTimeUpdate).toHaveBeenCalledWith(754)
  })

  test("does not move the position when there is no timestamp hash", () => {
    const { onTimeUpdate, video } = renderPlayer()

    fireEvent.loadedData(video)

    expect(video.currentTime).toBe(0)
    expect(onTimeUpdate).not.toHaveBeenCalled()
  })
})
