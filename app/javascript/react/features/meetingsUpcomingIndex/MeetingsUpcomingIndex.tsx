import dayjs from "dayjs"
import { useMemo, useRef } from "react"

import { MeetingsListHeader } from "~/react/composites/meetings/MeetingsListHeader"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { useCalendarConnection } from "~/react/shared/hooks/useCalendarConnection"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import type { MeetingResponse } from "~/react/shared/types"
import { formatDateTime } from "~/react/ui/DateTime"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadMoreSentinel } from "~/react/ui/LoadMoreSentinel"
import { CalendarConnectionPrompt } from "./components/CalendarConnectionPrompt"
import { UpcomingDateGroup } from "./components/UpcomingDateGroup"
import { useNowTick } from "./hooks/useNowTick"
import { useUpcomingMeetings } from "./hooks/useUpcomingMeetings"
import type { MeetingsUpcomingIndexProps } from "./types"
import { UpcomingListSkeleton } from "./UpcomingListSkeleton"

export function MeetingsUpcomingIndex({ googleCalendarLoginUrl }: MeetingsUpcomingIndexProps) {
  const { calendar, loading: calendarLoading } = useCalendarConnection()
  const { user } = useCurrentUser()
  const timezone = user?.time_zone ?? null
  const view = useUpcomingMeetings(timezone)
  const now = useNowTick()
  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef, [view.meetings])

  // Day keys use the user's configured tz (not browser-local) so bucketing and
  // the Today/Tomorrow headers reflect the user's day boundaries.
  const todayKey = formatDateTime(now.toISOString(), "date_iso_8601", { timezone })
  const tomorrowKey = dayjs(todayKey).add(1, "day").format("YYYY-MM-DD")

  const grouped = useMemo(() => bucketByDate(view.meetings, timezone), [view.meetings, timezone])
  const concurrentNextIds = useMemo(
    () => concurrentNextMeetingIds(view.meetings, todayKey, timezone),
    [view.meetings, todayKey, timezone]
  )

  // Only Google-authed users can initiate the Google Calendar OAuth
  // handshake, so the prompt is gated on that flag.
  const showCalendarPrompt = calendar && !calendar.calendar_connected && calendar.is_google_authenticated

  return (
    <div ref={rootRef}>
      <MeetingsListHeader current="upcoming" onMeetingCreated={meeting => boostedNavigate(meeting.source_url)} />
      <div className="px-2">
        {showCalendarPrompt ? (
          <CalendarConnectionPrompt googleCalendarLoginUrl={googleCalendarLoginUrl} />
        ) : (view.loading || calendarLoading) && view.meetings.length === 0 ? (
          // Wait for the calendar fetch too: an empty list could still resolve
          // into the Connect-Calendar prompt, so showing the empty state before
          // `calendar` is known would flash the wrong content.
          <UpcomingListSkeleton />
        ) : view.error ? (
          <ErrorState message="Failed to load upcoming meetings. Please try refreshing the page." />
        ) : view.meetings.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <span className="material-symbols-outlined text-4xl text-base-400 mb-2">event_available</span>
            <p className="text-base-500 text-sm">
              {calendar && !calendar.is_google_authenticated
                ? "Meeting recording is available for Google accounts."
                : "No upcoming meetings"}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {grouped.map(([dateKey, meetings]) => (
              <UpcomingDateGroup
                key={dateKey}
                dateKey={dateKey}
                todayKey={todayKey}
                tomorrowKey={tomorrowKey}
                meetings={meetings}
                concurrentNextMeetingIds={concurrentNextIds}
                timezone={timezone}
              />
            ))}
            {view.hasMore && <LoadMoreSentinel onIntersect={view.loadMore} loading={view.loadingMore} />}
          </div>
        )}
      </div>
    </div>
  )
}

function bucketByDate(meetings: MeetingResponse[], timezone: string | null): [string, MeetingResponse[]][] {
  const groups = new Map<string, MeetingResponse[]>()
  for (const meeting of meetings) {
    if (!meeting.scheduled_at) continue
    const key = formatDateTime(meeting.scheduled_at, "date_iso_8601", { timezone })
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(meeting)
  }
  return [...groups.entries()]
}

// Among meetings scheduled *today* (user tz) that are neither completed nor
// declined, find the earliest start; every meeting starting at that same instant
// is the "next" concurrent set and renders highlighted. Today-scoped — a future
// day's earliest meeting is never highlighted.
function concurrentNextMeetingIds(
  meetings: MeetingResponse[],
  todayKey: string,
  timezone: string | null
): Set<string> {
  const todays = meetings.filter(
    m =>
      m.scheduled_at &&
      !m.is_completed &&
      !m.is_declined &&
      formatDateTime(m.scheduled_at, "date_iso_8601", { timezone }) === todayKey
  )
  if (todays.length === 0) return new Set()
  const earliest = todays.reduce((min, m) =>
    new Date(m.scheduled_at!).getTime() < new Date(min.scheduled_at!).getTime() ? m : min
  )
  return new Set(todays.filter(m => m.scheduled_at === earliest.scheduled_at).map(m => m.id))
}
