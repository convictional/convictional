import * as Sentry from "@sentry/browser"
import { useEffect, useState } from "react"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import type { PostViewsResponse } from "~/react/shared/types"
import { formatDateTime } from "~/react/ui/DateTime"
import { Tooltip } from "~/react/ui/Tooltip"

interface ReadAnalyticsProps {
  postId: string
  // Only creators/admins may read analytics; the endpoint 403s otherwise, so the
  // island gates the fetch on the post's permissions to avoid a noisy request.
  enabled: boolean
}

function percent(part: number, whole: number): number {
  return whole > 0 ? Math.round((part / whole) * 100) : 0
}

// Read-analytics row (seen counts, group reach, sparkline). This data lives on
// GET /api/posts/{id}/views rather than the show payload, so the component
// fetches on mount, derives percentages and the sparkline max locally, and
// renders nothing on 403 or before data loads.
export function ReadAnalytics({ postId, enabled }: ReadAnalyticsProps) {
  const [views, setViews] = useState<PostViewsResponse | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    apiFetch<PostViewsResponse>(`/api/posts/${postId}/views`)
      .then(data => {
        if (!cancelled) setViews(data)
      })
      .catch(err => {
        // 403 means this viewer isn't a creator/admin — silently render nothing.
        // Report anything unexpected (network, parse) to Sentry; skip aborts, which
        // are normal request cancellations (e.g. navigation).
        if (err instanceof DOMException && err.name === "AbortError") return
        if (!(err instanceof ApiError)) Sentry.captureException(err)
      })
    return () => {
      cancelled = true
    }
  }, [postId, enabled])

  if (!views) return null

  const seenPercent = percent(views.seen_count, views.total_audience)
  const sparklineMax = Math.max(1, ...views.views.map(v => v.count))
  const seenTooltip = `Seen by ${views.seen_count} of ${views.total_audience} people (${seenPercent}%)`
  const firstSeenTooltip = views.first_seen_at
    ? `First viewed ${formatDateTime(views.first_seen_at, "relative")}`
    : undefined

  return (
    <div className="flex items-center gap-2 px-3 py-2 border-t border-base-300 text-xs text-base-500">
      <span className="material-symbols-outlined text-sm">visibility</span>
      {views.group && (
        <>
          <Tooltip content={`${views.group.seen_count} of ${views.group.total_audience} in ${views.group.name}`}>
            <span>
              <span className="font-medium">{views.group.seen_count}</span> of {views.group.total_audience} in{" "}
              {views.group.name}
            </span>
          </Tooltip>
          <span className="text-base-500">·</span>
        </>
      )}
      <Tooltip content={seenTooltip}>
        <span>
          <span className="font-medium">{views.seen_count}</span> of {views.total_audience}{" "}
          {views.group ? "total" : ""}
        </span>
      </Tooltip>
      {views.views.length > 0 && (
        <>
          <span className="text-base-500">·</span>
          <Tooltip content={firstSeenTooltip ?? "Views over time"}>
            <span className="flex items-end gap-px h-3">
              {views.views.map(bucket => (
                <span
                  key={bucket.window_start}
                  className={`w-1.5 rounded-t-sm ${bucket.count > 0 ? "bg-base-500" : "bg-base-400/30"}`}
                  style={{ height: `${Math.max(10, (bucket.count / sparklineMax) * 100)}%` }}
                />
              ))}
            </span>
          </Tooltip>
        </>
      )}
    </div>
  )
}
