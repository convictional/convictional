import { useCallback, useEffect, useRef, useState } from "react"

import { usePreviewStream } from "~/react/features/research/scheduled/hooks/usePreviewStream"
import { ScheduledResearchFrequency, type ScheduledResearch } from "~/react/features/research/scheduled/types"
import { apiFetch } from "~/react/shared/apiFetch"
import { formatDateTime } from "~/react/ui/DateTime"
import { showFlash } from "~/shared/flash"

export const OPEN_EVENT = "research-dialog:open"
export const CLOSED_EVENT = "research-dialog:closed"
export const SCHEDULED_RESEARCH_CHANGED_EVENT = "scheduled-research:changed"

export type ResearchDialogMode = "once" | "schedule"

export type ScheduledResearchChangedDetail =
  | { action: "created"; item: ScheduledResearch }
  | { action: "updated"; item: ScheduledResearch }
  | { action: "deleted"; id: string }

export interface OpenResearchDialogDetail {
  mode?: ResearchDialogMode
  prefill?: { prompt?: string }
  schedule?: ScheduledResearch
}

export function openResearchDialog(detail: OpenResearchDialogDetail = {}): void {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail }))
}

interface CreateResponse {
  id: string
}

export type RunState = "idle" | "running" | "just_ran"

const DEFAULT_FREQUENCY = ScheduledResearchFrequency.WEEKLY
const DEFAULT_HOUR = 9
const DEFAULT_DAY_OF_WEEK = "1"
const JUST_RAN_DURATION_MS = 3000
const SCHEDULED_RESEARCH_PATH = "/scheduled_research"

function dispatchChange(detail: ScheduledResearchChangedDetail) {
  window.dispatchEvent(new CustomEvent(SCHEDULED_RESEARCH_CHANGED_EVENT, { detail }))
}

function formatFirstDeliveryFlash(item: ScheduledResearch, timezone: string | null): string {
  // Sets the user's expectation immediately: a schedule does not deliver on creation, so the
  // confirmation needs to name the first run explicitly.
  if (!item.next_run_at) return "Schedule created."
  const when = formatDateTime(item.next_run_at, "weekday_short_month_day_time_tz", { timezone })
  return `Schedule created. First research arrives ${when}.`
}

export interface UseResearchDialogOptions {
  currentUserTimezone?: string | null
}

export function useResearchDialog({ currentUserTimezone = null }: UseResearchDialogOptions = {}) {
  const [isOpen, setIsOpen] = useState(false)
  const [body, setBodyState] = useState("")
  const [mode, setMode] = useState<ResearchDialogMode>("once")
  const [frequency, setFrequency] = useState<ScheduledResearchFrequency>(DEFAULT_FREQUENCY)
  const [hour, setHour] = useState<number>(DEFAULT_HOUR)
  const [dayOfWeek, setDayOfWeek] = useState<string>(DEFAULT_DAY_OF_WEEK)
  const [scheduleId, setScheduleId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [runState, setRunState] = useState<RunState>("idle")
  const [error, setError] = useState<string | null>(null)
  const preview = usePreviewStream()
  const { reset: resetPreview, status: previewStatus, start: startPreviewStream } = preview

  // The element that had focus when the dialog opened — restored on close so keyboard users
  // don't lose their place in the nav.
  const previouslyFocused = useRef<HTMLElement | null>(null)
  const runNowTimerRef = useRef<number | null>(null)

  const clearRunNowTimer = () => {
    if (runNowTimerRef.current !== null) {
      window.clearTimeout(runNowTimerRef.current)
      runNowTimerRef.current = null
    }
  }

  useEffect(() => {
    const handleOpen = (event: Event) => {
      const detail = (event as CustomEvent<OpenResearchDialogDetail>).detail ?? {}
      const editing = detail.schedule
      const nextMode: ResearchDialogMode = editing || detail.mode === "schedule" ? "schedule" : "once"
      previouslyFocused.current = document.activeElement as HTMLElement | null
      setError(null)
      setRunState("idle")
      setMode(nextMode)
      if (editing) {
        setScheduleId(editing.id)
        setBodyState(editing.prompt)
        setFrequency(editing.frequency)
        setHour(editing.hour)
        setDayOfWeek(editing.day_of_week ?? DEFAULT_DAY_OF_WEEK)
      } else {
        setScheduleId(null)
        // Schedule fields get fresh defaults each open — carrying a stale cadence from a prior
        // session would be surprising.
        setFrequency(DEFAULT_FREQUENCY)
        setHour(DEFAULT_HOUR)
        setDayOfWeek(DEFAULT_DAY_OF_WEEK)
        if (typeof detail.prefill?.prompt === "string") {
          setBodyState(detail.prefill.prompt)
        }
      }
      resetPreview()
      setIsOpen(true)
    }
    window.addEventListener(OPEN_EVENT, handleOpen)
    return () => window.removeEventListener(OPEN_EVENT, handleOpen)
  }, [resetPreview])

  // Editing the prompt after a preview invalidates it — drop the stale content so the user
  // isn't misled while typing.
  const setBody = useCallback(
    (next: string) => {
      if (previewStatus !== "idle") resetPreview()
      setBodyState(next)
    },
    [previewStatus, resetPreview]
  )

  const close = useCallback(() => {
    setIsOpen(false)
    setScheduleId(null)
    setRunState("idle")
    setSubmitting(false)
    clearRunNowTimer()
    resetPreview()
    previouslyFocused.current?.focus?.()
    window.dispatchEvent(new CustomEvent(CLOSED_EVENT))
  }, [resetPreview])

  // Mutations shouldn't leave their prompt in the textarea for the next open; Escape/cancel
  // should (a user may be stepping away and want to finish later).
  const closeAfterSuccess = useCallback(() => {
    setBodyState("")
    close()
  }, [close])

  const toggleMode = useCallback(() => {
    setMode(prev => {
      const next: ResearchDialogMode = prev === "schedule" ? "once" : "schedule"
      if (next === "once") resetPreview()
      return next
    })
  }, [resetPreview])

  const isEditing = scheduleId !== null

  const submit = useCallback(async () => {
    const trimmed = body.trim()
    if (!trimmed || submitting) return

    setSubmitting(true)
    setError(null)
    try {
      if (mode === "schedule") {
        const payload = {
          prompt: trimmed,
          frequency,
          hour,
          day_of_week: frequency === ScheduledResearchFrequency.WEEKLY ? dayOfWeek : null,
        }
        if (scheduleId) {
          const updated = await apiFetch<ScheduledResearch>(`/api/scheduled_research/${scheduleId}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
          })
          dispatchChange({ action: "updated", item: updated })
          closeAfterSuccess()
          return
        }
        const created = await apiFetch<ScheduledResearch>("/api/scheduled_research", {
          method: "POST",
          body: JSON.stringify(payload),
        })
        // Patch the list in place if it's already open; either way the user stays where they
        // were — the flash is the confirmation and the link inside it routes to the list on demand.
        const message = formatFirstDeliveryFlash(created, currentUserTimezone)
        if (window.location.pathname === SCHEDULED_RESEARCH_PATH) {
          dispatchChange({ action: "created", item: created })
          showFlash(message, "success")
        } else {
          showFlash(message, "success", SCHEDULED_RESEARCH_PATH)
        }
        closeAfterSuccess()
      } else {
        await apiFetch<CreateResponse>("/api/research_questions", {
          method: "POST",
          body: JSON.stringify({ body: trimmed }),
        })
        // Reload to re-render inbox progress on the mailbox (or no-op on other pages) —
        // matches the HTML form's redirect_back_or behaviour.
        window.location.reload()
      }
    } catch {
      setSubmitting(false)
      setError("Something went wrong")
    }
  }, [body, submitting, mode, frequency, hour, dayOfWeek, scheduleId, closeAfterSuccess, currentUserTimezone])

  const deleteSchedule = useCallback(async () => {
    if (!scheduleId || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await apiFetch(`/api/scheduled_research/${scheduleId}`, { method: "DELETE" })
      dispatchChange({ action: "deleted", id: scheduleId })
      closeAfterSuccess()
    } catch {
      setSubmitting(false)
      setError("Couldn't delete the schedule.")
    }
  }, [scheduleId, submitting, closeAfterSuccess])

  const runNow = useCallback(async () => {
    if (!scheduleId || runState !== "idle") return
    setError(null)
    setRunState("running")
    try {
      await apiFetch(`/api/scheduled_research/${scheduleId}/run_now`, { method: "POST" })
      setRunState("just_ran")
      clearRunNowTimer()
      runNowTimerRef.current = window.setTimeout(() => {
        runNowTimerRef.current = null
        setRunState("idle")
      }, JUST_RAN_DURATION_MS)
    } catch {
      setRunState("idle")
      setError("Couldn't enqueue the schedule.")
    }
  }, [scheduleId, runState])

  const startPreview = useCallback(() => {
    const trimmed = body.trim()
    if (!trimmed) return
    void startPreviewStream(trimmed)
  }, [body, startPreviewStream])

  return {
    isOpen,
    body,
    mode,
    frequency,
    hour,
    dayOfWeek,
    scheduleId,
    isEditing,
    submitting,
    runState,
    error,
    preview,
    setBody,
    setFrequency,
    setHour,
    setDayOfWeek,
    toggleMode,
    close,
    submit,
    deleteSchedule,
    runNow,
    startPreview,
  }
}
