import { useCallback, useEffect, useRef, useState } from "react"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"

import type { ProcessedTranscript, TranscriptLine } from "../types"

export type TranscriptStatus =
  { kind: "loading" } | { kind: "processing" } | { kind: "loaded"; lines: TranscriptLine[] }

export function useTranscript(meetingId: string, isProcessing: boolean): TranscriptStatus {
  const [status, setStatus] = useState<TranscriptStatus>({ kind: "loading" })

  // Read the latest processing flag inside the async 404 handler without making
  // it a dependency of fetchTranscript — otherwise the mount fetch would re-run
  // on every flag flip.
  const isProcessingRef = useRef(isProcessing)
  useEffect(() => {
    isProcessingRef.current = isProcessing
  }, [isProcessing])

  const fetchTranscript = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const response = await apiFetch<ProcessedTranscript>(`/api/meetings/${meetingId}/transcript`, { signal })
        if (signal?.aborted) return
        setStatus({ kind: "loaded", lines: response.lines })
      } catch (error) {
        if (signal?.aborted) return
        // 404 means there's no processed transcript yet. If a bot or an upload
        // job is still working, show the processing spinner and let the
        // false-edge below re-fetch once it finishes. Otherwise the meeting
        // simply has no transcript (e.g. an uploaded recording that was never
        // transcribed, or any meeting with no Recall bot) — render the empty
        // state rather than spinning forever on a callback that never fires.
        if (error instanceof ApiError && error.status === 404) {
          setStatus(isProcessingRef.current ? { kind: "processing" } : { kind: "loaded", lines: [] })
          return
        }
        throw error
      }
    },
    [meetingId]
  )

  useEffect(() => {
    const controller = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchTranscript(controller.signal)
    return () => controller.abort()
  }, [fetchTranscript])

  const previousProcessingRef = useRef(isProcessing)
  useEffect(() => {
    if (previousProcessingRef.current && !isProcessing) {
      void fetchTranscript()
    }
    previousProcessingRef.current = isProcessing
  }, [isProcessing, fetchTranscript])

  return status
}
