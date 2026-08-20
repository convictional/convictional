import { useCallback, useEffect, useRef, useState } from "react"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"

import type { MeetingBotState, MeetingDetail } from "../types"

interface State {
  meeting: MeetingDetail | null
  bot: MeetingBotState | null
  loading: boolean
  error: boolean
}

// Tracks per-field local edit timestamps so a server refetch (window focus,
// future channel push) can't clobber an in-flight optimistic mutation.
// Compared against the response receive time — older responses lose.
export type MutatedAt = Partial<Record<keyof MeetingDetail, number>>

export function useMeetingShow(meetingId: string) {
  const [state, setState] = useState<State>({ meeting: null, bot: null, loading: true, error: false })
  const mutatedAtRef = useRef<MutatedAt>({})

  const fetchAll = useCallback(
    async (signal?: AbortSignal) => {
      const fetchedAt = Date.now()
      try {
        const [meeting, bot] = await Promise.all([
          apiFetch<MeetingDetail>(`/api/meetings/${meetingId}`, { signal }),
          // 404 means no Recall.ai bot for this meeting (text-only / uploaded
          // video meetings) — that's a normal state, not an error. Declaring it
          // expected keeps the 404 out of Sentry while still letting us branch.
          apiFetch<MeetingBotState>(`/api/meetings/${meetingId}/bot`, { signal }, { expectedStatuses: [404] }).catch(
            error => {
              if (error instanceof ApiError && error.status === 404) return null
              throw error
            }
          ),
        ])
        if (signal?.aborted) return
        setState(prev => ({
          meeting: mergeWithLocalEdits(meeting, prev.meeting, mutatedAtRef.current, fetchedAt),
          bot,
          loading: false,
          error: false,
        }))
      } catch (error) {
        if (signal?.aborted) return
        if (error instanceof ApiError && error.status === 401) return
        setState(prev => ({ ...prev, loading: false, error: true }))
      }
    },
    [meetingId]
  )

  useEffect(() => {
    const controller = new AbortController()
    void fetchAll(controller.signal)
    return () => controller.abort()
  }, [fetchAll])

  // Refetch on window focus so a meeting left open in a background tab catches
  // up on edits made elsewhere (other tab, mobile, collaborator).
  useEffect(() => {
    const onFocus = () => void fetchAll()
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [fetchAll])

  const applyLocalUpdate = useCallback(<K extends keyof MeetingDetail>(field: K, value: MeetingDetail[K]) => {
    mutatedAtRef.current = { ...mutatedAtRef.current, [field]: Date.now() }
    setState(prev => (prev.meeting ? { ...prev, meeting: { ...prev.meeting, [field]: value } } : prev))
  }, [])

  const applyServerUpdate = useCallback((meeting: MeetingDetail) => {
    setState(prev => ({
      ...prev,
      meeting: mergeWithLocalEdits(meeting, prev.meeting, mutatedAtRef.current, Date.now()),
    }))
  }, [])

  // Bot state has no local optimistic edits, so server pushes win
  // unconditionally — no per-field mutatedAt tracking like meeting fields above.
  const applyBotUpdate = useCallback((bot: MeetingBotState) => {
    setState(prev => ({ ...prev, bot }))
  }, [])

  return { ...state, applyLocalUpdate, applyServerUpdate, applyBotUpdate, refetch: fetchAll }
}

// `baseline` is the timestamp the incoming payload reflects the world as of —
// fetch-start for HTTP responses, receive time for channel pushes. Any local
// edit stamped after that baseline beats the incoming value for that field.
function mergeWithLocalEdits(
  incoming: MeetingDetail,
  current: MeetingDetail | null,
  mutatedAt: MutatedAt,
  baseline: number
): MeetingDetail {
  if (!current) return incoming
  const merged = { ...incoming }
  for (const field of Object.keys(mutatedAt) as (keyof MeetingDetail)[]) {
    const stamp = mutatedAt[field]
    if (stamp !== undefined && stamp > baseline) {
      ;(merged as Record<string, unknown>)[field as string] = current[field]
    }
  }
  return merged
}
