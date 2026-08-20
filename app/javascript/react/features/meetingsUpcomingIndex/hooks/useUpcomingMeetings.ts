import { useEffect, useRef } from "react"

import { usePaginatedList } from "~/react/shared/hooks/usePaginatedList"
import type { MeetingListResponse, MeetingResponse } from "~/react/shared/types"
import { startOfDayIso } from "~/react/ui/DateTime"

function buildUrl(timezone: string | null, cursor: string | null): string {
  // Recomputing the day window on every fetch (rather than caching it) lets a
  // tab open across midnight roll forward when it next refetches. Start-of-day
  // is computed in the user's tz so the window matches the server's
  // `datetime.now(helpers.timezone)` boundary, not the browser's.
  const params = new URLSearchParams({
    scheduled_after: startOfDayIso(new Date(), timezone),
    sort: "scheduled_at_asc",
    // `member` scopes to meetings the user created or collaborates on, and
    // `include_declined` keeps declined meetings in the list so they render
    // struck-through rather than vanishing.
    scope: "member",
    include_declined: "true",
  })
  if (cursor) params.set("cursor", cursor)
  return `/api/meetings?${params.toString()}`
}

export function useUpcomingMeetings(timezone: string | null) {
  // True once the user has loaded a page beyond the first. The tab-focus
  // refetch resets to page 1, which would discard already-loaded pages and the
  // scroll position, so we skip it once the list has been paginated.
  const paginatedRef = useRef(false)

  const { items, loading, loadingMore, error, hasMore, loadMore, reload } = usePaginatedList<
    MeetingResponse,
    MeetingListResponse
  >({
    buildUrl: cursor => buildUrl(timezone, cursor),
    select: data => data.meetings,
    deps: [timezone],
    onPage: (_data, { isLoadMore }) => {
      paginatedRef.current = isLoadMore
    },
  })

  useEffect(() => {
    function onVisibility() {
      // Roll the day window forward (e.g. across midnight) and pick up new
      // meetings on tab focus — but only while still on the first page, since a
      // refetch rebuilds from page 1 and would lose loaded pages / scroll.
      if (document.visibilityState === "visible" && !paginatedRef.current) reload()
    }
    document.addEventListener("visibilitychange", onVisibility)
    return () => document.removeEventListener("visibilitychange", onVisibility)
  }, [reload])

  return { meetings: items, loading, loadingMore, error, hasMore, loadMore }
}
