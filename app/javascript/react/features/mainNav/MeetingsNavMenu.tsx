import { useEffect, useMemo, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { useActiveRoute } from "~/react/shared/hooks/useActiveRoute"
import { NavLink } from "~/react/shared/NavLink"
import type { PaginatedResponse } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"
import { Tooltip } from "~/react/ui/Tooltip"

interface MeetingApi {
  id: string
  title: string | null
  scheduled_at: string
  scheduled_end_at: string | null
  is_completed: boolean
  is_happening_now: boolean
  source_url: string
}

interface MeetingListApi extends PaginatedResponse {
  meetings: MeetingApi[]
}

interface PillState {
  next: MeetingApi | null
  // Number of meetings starting at the same time as `next` — drives the
  // "N upcoming · <time>" copy when several meetings share a start.
  simultaneousCount: number
}

const POLL_INTERVAL_MS = 30_000

function pillStateFor(meetings: MeetingApi[]): PillState {
  const next = meetings.find(m => !m.is_completed) ?? null
  if (!next) return { next: null, simultaneousCount: 0 }
  const simultaneousCount = meetings.filter(m => m.scheduled_at === next.scheduled_at).length
  return { next, simultaneousCount }
}

export function MeetingsNavMenu() {
  const pathname = useActiveRoute()
  const [meetings, setMeetings] = useState<MeetingApi[] | null>(null)

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null
    let cancelled = false

    const refresh = async () => {
      try {
        // Recompute the day window every poll so a tab open across midnight
        // rolls forward without a reload.
        const start = new Date()
        start.setHours(0, 0, 0, 0)
        const end = new Date(start)
        end.setDate(end.getDate() + 1)
        const params = new URLSearchParams({
          scope: "member",
          scheduled_after: start.toISOString(),
          scheduled_before: end.toISOString(),
          completed: "false",
          sort: "scheduled_at_asc",
        })
        const data = await apiFetch<MeetingListApi>(`/api/meetings?${params}`)
        if (cancelled) return
        setMeetings(data.meetings)
      } catch {
        // Keep the last successful response visible — transient failures
        // shouldn't blank the pill once we've shown data.
      }
    }

    const start = () => {
      if (intervalId !== null) return
      intervalId = setInterval(refresh, POLL_INTERVAL_MS)
    }
    const stop = () => {
      if (intervalId === null) return
      clearInterval(intervalId)
      intervalId = null
    }

    refresh()
    if (document.visibilityState === "visible") start()

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        refresh()
        start()
      } else {
        stop()
      }
    }
    document.addEventListener("visibilitychange", onVisibility)

    return () => {
      cancelled = true
      stop()
      document.removeEventListener("visibilitychange", onVisibility)
    }
  }, [])

  const pill = useMemo<PillState | null>(() => (meetings ? pillStateFor(meetings) : null), [meetings])

  const isActive = pathname.startsWith("/meetings")
  const linkClasses = `grid grid-cols-[auto] sm:grid-cols-[auto_minmax(0,1fr)] items-center gap-0 sm:gap-1.5 px-1.5 sm:px-2.5 py-1 rounded-full transition-all cursor-pointer ${
    isActive ? "text-primary font-medium" : "text-base-content hover:text-primary"
  }`

  // Until the first fetch returns, render the skeleton-equivalent: just the
  // calendar icon. Server-side skeleton in the Jinja mount keeps geometry
  // stable while React hydrates.
  if (!pill) {
    return (
      <NavLink href="/meetings/upcoming" className={linkClasses} aria-label="Upcoming meetings">
        <span className="material-symbols-outlined text-sm">calendar_today</span>
      </NavLink>
    )
  }

  const tooltip = pill.next?.title ?? ""
  return (
    <Tooltip content={tooltip}>
      <NavLink href="/meetings/upcoming" className={linkClasses}>
        <span className="material-symbols-outlined text-sm">calendar_today</span>
        <PillCopy pill={pill} />
      </NavLink>
    </Tooltip>
  )
}

function PillCopy({ pill }: { pill: PillState }) {
  if (!pill.next) {
    return <span className="text-sm hidden sm:inline">No meetings today</span>
  }
  if (pill.simultaneousCount > 1) {
    return (
      <span className="text-sm min-w-0 flex items-baseline gap-1 hidden sm:inline-flex">
        <span className="truncate">{pill.simultaneousCount} upcoming</span>
        <span className="shrink-0">
          &middot; <DateTime datetime={pill.next.scheduled_at} format="relative" />
        </span>
      </span>
    )
  }
  return (
    <span className="text-sm min-w-0 flex items-baseline gap-1 hidden sm:inline-flex">
      <span className="truncate">{pill.next.title ?? "Untitled meeting"}</span>
      <span className="shrink-0">
        · {pill.next.is_happening_now ? "now" : <DateTime datetime={pill.next.scheduled_at} format="relative" />}
      </span>
    </span>
  )
}
