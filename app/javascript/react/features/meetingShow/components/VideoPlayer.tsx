import type { RefObject } from "react"
import { useCallback, useEffect, useRef } from "react"

import { useRecordingUrl } from "../hooks/useRecordingUrl"

interface VideoPlayerProps {
  meetingId: string
  hasRecording: boolean
  videoRef: RefObject<HTMLVideoElement | null>
  onTimeUpdate: (seconds: number) => void
}

// Throttle timeupdate to 250ms to keep the parent's currentTime state from
// re-rendering the transcript on every frame. Math.floor gives whole-second
// granularity, which is all the transcript line-highlighting needs.
const TIMEUPDATE_INTERVAL_MS = 250

export function VideoPlayer({ meetingId, hasRecording, videoRef, onTimeUpdate }: VideoPlayerProps) {
  const { url, missing } = useRecordingUrl(meetingId, hasRecording, videoRef)
  const lastTimeUpdateRef = useRef(0)

  const handleTimeUpdate = useCallback(() => {
    const now = performance.now()
    if (now - lastTimeUpdateRef.current < TIMEUPDATE_INTERVAL_MS) return
    lastTimeUpdateRef.current = now
    const videoEl = videoRef.current
    if (!videoEl) return
    onTimeUpdate(Math.floor(videoEl.currentTime))
  }, [videoRef, onTimeUpdate])

  // Seek the element and sync the lifted currentTime in the same step. We can't
  // rely on the native timeupdate to fan the new position back up here: with
  // preload="metadata" the hash seek can land before any playback, and a user
  // who copies a timestamp link without ever pressing play would otherwise get
  // the stale 0 the parent started at (the transcript highlight would be off for
  // the same reason).
  const seekTo = useCallback(
    (seconds: number) => {
      const videoEl = videoRef.current
      if (!videoEl) return
      videoEl.currentTime = seconds
      onTimeUpdate(Math.floor(seconds))
    },
    [videoRef, onTimeUpdate]
  )

  const handleLoadedData = useCallback(() => {
    const fragmentTime = parseTimestampFromHash()
    if (fragmentTime !== null) seekTo(fragmentTime)
  }, [seekTo])

  // Honour #timestamp-N on initial mount as well: the loadeddata handler covers
  // post-load and refresh, but a user landing on the page with a hash needs the
  // seek the moment the metadata is available.
  useEffect(() => {
    const videoEl = videoRef.current
    if (!videoEl) return
    const fragmentTime = parseTimestampFromHash()
    if (fragmentTime === null) return
    if (videoEl.readyState >= 1) seekTo(fragmentTime)
  }, [videoRef, url, seekTo])

  if (missing) {
    return (
      <div className="w-full h-full bg-base-200 flex items-center justify-center aspect-video">
        <p className="text-sm text-base-500">Recording unavailable.</p>
      </div>
    )
  }

  if (!url) {
    return (
      <div className="w-full h-full bg-base-200 flex items-center justify-center aspect-video">
        <span className="loading loading-spinner loading-md" />
      </div>
    )
  }

  return (
    <video
      ref={videoRef}
      controls
      preload="metadata"
      poster="/static/images/video_loading.jpg"
      className="w-full h-full object-contain"
      onTimeUpdate={handleTimeUpdate}
      onLoadedData={handleLoadedData}
    >
      <source src={url} type="video/mp4" />
    </video>
  )
}

function parseTimestampFromHash(): number | null {
  const hash = window.location.hash
  if (!hash.startsWith("#timestamp-")) return null
  const value = parseFloat(hash.slice("#timestamp-".length))
  return Number.isNaN(value) ? null : value
}
