import type { RefObject } from "react"
import { useCallback, useEffect, useRef, useState } from "react"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"

import type { MeetingRecording } from "../types"

// Owns the signed recording URL and the visibility-driven refresh. The URL is
// intentionally only refreshed when the tab becomes visible AND the video is
// paused — refreshing during playback would interrupt the stream, and if the
// URL has expired the next byte-range request will 403 and let the user take
// action. There's no TTL timer.
export function useRecordingUrl(
  meetingId: string,
  hasRecording: boolean,
  videoRef: RefObject<HTMLVideoElement | null>
) {
  const [url, setUrl] = useState<string | null>(null)
  const [missing, setMissing] = useState(false)
  // Prevent overlapping refreshes if visibilitychange fires while the previous
  // fetch is still in flight.
  const fetchingRef = useRef(false)

  const fetchUrl = useCallback(async () => {
    if (fetchingRef.current) return null
    fetchingRef.current = true
    try {
      // A 404 means the recording is genuinely absent (deleted, never produced) —
      // expected control flow, so keep it out of Sentry.
      const response = await apiFetch<MeetingRecording>(
        `/api/meetings/${meetingId}/recording`,
        {},
        { expectedStatuses: [404] }
      )
      setMissing(false)
      return response.url
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setMissing(true)
        return null
      }
      throw error
    } finally {
      fetchingRef.current = false
    }
  }, [meetingId])

  useEffect(() => {
    if (!hasRecording) return
    let cancelled = false
    void fetchUrl().then(initial => {
      if (!cancelled && initial) setUrl(initial)
    })
    return () => {
      cancelled = true
    }
  }, [hasRecording, fetchUrl])

  useEffect(() => {
    if (!hasRecording) return
    const onVisibilityChange = async () => {
      if (document.visibilityState !== "visible") return
      const videoEl = videoRef.current
      // Don't interrupt active playback — the browser will keep streaming from
      // the current URL until it expires mid-byte-range.
      if (!videoEl || !videoEl.paused) return
      const previousTime = videoEl.currentTime
      const refreshed = await fetchUrl()
      if (!refreshed || refreshed === url) return
      setUrl(refreshed)
      // Updating React state re-renders <source src>, but the browser ignores a
      // <source> src change after the initial load — the media element only
      // re-fetches when load() is called. Set the src imperatively and reload so
      // the refreshed signed URL actually takes effect. Without this the refresh
      // is inert and an expired URL would still 403 on the next byte-range request.
      const sourceEl = videoEl.querySelector("source")
      if (sourceEl) sourceEl.src = refreshed
      videoEl.load()
      // {once:true} is critical — `loadeddata` also fires on the initial src
      // load, and re-running this handler would re-seek on every reload.
      videoEl.addEventListener(
        "loadeddata",
        () => {
          videoEl.currentTime = previousTime
        },
        { once: true }
      )
    }
    document.addEventListener("visibilitychange", onVisibilityChange)
    return () => document.removeEventListener("visibilitychange", onVisibilityChange)
  }, [hasRecording, fetchUrl, videoRef, url])

  return { url, missing }
}
