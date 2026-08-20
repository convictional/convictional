import { useCallback, useEffect, useRef, useState } from "react"

import {
  SCHEDULED_RESEARCH_CHANGED_EVENT,
  openResearchDialog,
  type ScheduledResearchChangedDetail,
} from "~/react/features/research/dialog/hooks/useResearchDialog"
import { apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { EmptyState } from "~/react/ui/EmptyState"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { showFlash } from "~/shared/flash"

import { SCHEDULE_ROW_GRID_COLS, ScheduleRow } from "./components/ScheduleRow"
import { useScheduledResearchData } from "./hooks/useScheduledResearchData"
import { formatTimezoneAbbr } from "./timezone"
import type { ScheduledResearchPrefillResponse } from "./types"

// Keep these in sync with SUGGESTIONS in ResearchDialog.tsx so the empty state and the in-dialog
// pills offer the same starter prompts.
const EXAMPLE_PROMPTS: { title: string; prompt: string }[] = [
  {
    title: "Catch me up on last week",
    prompt: "Catch me up on work from last week. Use bullet points, no more than 10.",
  },
  { title: "Generate my to-do list", prompt: "Generate my to-do list based on the past day." },
]

function openCreateDialog(prefill?: { prompt?: string }) {
  openResearchDialog({ mode: "schedule", ...(prefill ? { prefill } : {}) })
}

function readInitialHash(): string | null {
  const id = window.location.hash.replace(/^#/, "")
  return id || null
}

export function ScheduledResearchIndex() {
  const data = useScheduledResearchData()
  const { user } = useCurrentUser()
  const [initialHashId] = useState<string | null>(readInitialHash)
  const hashHandledRef = useRef(false)
  const prefillFetchHandledRef = useRef(false)

  // Email linkback (?prefill_from=<id>) needs an API lookup, then hands the prompt to the
  // global research dialog via the same open event the + button uses.
  useEffect(() => {
    if (prefillFetchHandledRef.current) return
    prefillFetchHandledRef.current = true

    const params = new URLSearchParams(window.location.search)
    const prefillFrom = params.get("prefill_from")
    if (!prefillFrom) return

    // Clear the URL param so a refresh doesn't re-trigger the dialog.
    params.delete("prefill_from")
    const qs = params.toString()
    const newUrl = `${window.location.pathname}${qs ? `?${qs}` : ""}${window.location.hash}`
    window.history.replaceState(null, "", newUrl)

    apiFetch<ScheduledResearchPrefillResponse>(
      `/api/scheduled_research/prefill?from_research_question=${encodeURIComponent(prefillFrom)}`
    )
      .then(resp => {
        openCreateDialog({ prompt: resp.prompt })
      })
      .catch(() => {
        showFlash("Couldn't load the research to schedule.")
      })
  }, [])

  // Hash deeplink: once the list resolves, if #<id> matches a loaded row, open the dialog for
  // it and clear the hash. Rows paginated off-screen are left alone (user can Load more).
  useEffect(() => {
    if (hashHandledRef.current || !initialHashId || data.items.length === 0) return
    const match = data.items.find(s => s.id === initialHashId)
    if (!match) return
    hashHandledRef.current = true

    const el = document.getElementById(`schedule-${initialHashId}`)
    if (el) window.requestAnimationFrame(() => el.scrollIntoView({ behavior: "smooth", block: "start" }))

    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`)
    openResearchDialog({ mode: "schedule", schedule: match })
  }, [initialHashId, data.items])

  const { applyCreated, applyUpdated, applyDeleted } = data
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<ScheduledResearchChangedDetail>).detail
      if (!detail) return
      if (detail.action === "created") applyCreated(detail.item)
      else if (detail.action === "updated") applyUpdated(detail.item)
      else if (detail.action === "deleted") applyDeleted(detail.id)
    }
    window.addEventListener(SCHEDULED_RESEARCH_CHANGED_EVENT, handler)
    return () => window.removeEventListener(SCHEDULED_RESEARCH_CHANGED_EVENT, handler)
  }, [applyCreated, applyUpdated, applyDeleted])

  const handleCreate = useCallback(() => {
    openCreateDialog()
  }, [])

  const tzAbbr = formatTimezoneAbbr(user?.time_zone ?? null)

  return (
    <div data-testid="scheduled-research-index">
      <StickyHeader>
        <div className="flex items-center justify-between gap-2 p-2">
          <h1 className="text-lg font-accent px-1">Scheduled research</h1>
          <button
            type="button"
            onClick={handleCreate}
            data-testid="scheduled-research-new-button"
            className="btn btn-primary"
          >
            <span className="material-symbols-outlined text-lg">add</span>
            New schedule
          </button>
        </div>
      </StickyHeader>

      {data.loading && (
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner loading-sm"></span>
        </div>
      )}

      {!data.loading && data.error && (
        <div className="px-4 py-12 text-center text-sm text-base-content/60">
          Couldn&rsquo;t load scheduled research.{" "}
          <button type="button" className="link" onClick={() => data.refetch()}>
            Retry
          </button>
          .
        </div>
      )}

      {!data.loading && !data.error && data.items.length === 0 && (
        <div data-testid="scheduled-research-empty">
          <EmptyState
            title="No scheduled research yet."
            text="Have AI research a topic on a cadence — a Monday catch-up, a daily to-do list — and receive it by email."
          >
            <div className="flex items-center justify-center gap-1 flex-wrap">
              {EXAMPLE_PROMPTS.map(prompt => (
                <button
                  key={prompt.title}
                  type="button"
                  onClick={() => openCreateDialog({ prompt: prompt.prompt })}
                  className="py-1.5 px-3 rounded-full text-sm text-base-content/50 hover:text-base-content hover:bg-base-200 transition-colors cursor-pointer"
                >
                  {prompt.title}
                </button>
              ))}
            </div>
          </EmptyState>
        </div>
      )}

      {!data.loading && !data.error && data.items.length > 0 && (
        <div>
          <div
            className={`grid ${SCHEDULE_ROW_GRID_COLS} border-b border-base-300 text-xs uppercase text-base-content/60 font-semibold`}
          >
            <div className="px-4 py-2">Title</div>
            <div className="px-4 py-2">Cadence</div>
            <div className="px-4 py-2">Next run</div>
          </div>
          <ul>
            {data.items.map(schedule => (
              <li key={schedule.id} id={`schedule-${schedule.id}`}>
                <ScheduleRow schedule={schedule} tzAbbr={tzAbbr} />
              </li>
            ))}
            {data.hasMore && (
              <li className="flex justify-center py-2">
                <button
                  type="button"
                  className="py-1.5 px-4 rounded-full text-sm text-base-content/60 hover:text-base-content hover:bg-base-200 transition-colors cursor-pointer disabled:opacity-50"
                  onClick={data.loadMore}
                  disabled={data.loadingMore}
                >
                  {data.loadingMore ? "Loading…" : "Load more"}
                </button>
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
