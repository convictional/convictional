import type { PaginatedResponse, User } from "~/react/shared/types"

export interface GoalAlignmentsShowProps {
  goalId: string
}

// Slim content shape carried by an alignment. Mirrors the fields the card reads
// from `app.routers.api.schemas.ContentResponse`; the API returns the full
// ContentResponse but we only consume these.
export interface AlignmentContent {
  id: string
  title: string
  author: string | null
  content_type: string
  source_url: string
}

// Mirrors `app.routers.api.goal_alignments.GoalAlignmentResponse`. `score` is the
// model property (1.0 when pinned, else alignment_score); both are sent so the UI
// can reflect pin semantics without re-deriving them.
export interface GoalAlignment {
  id: string
  content: AlignmentContent
  signal: string
  alignment_score: number
  score: number
  pinned: boolean
  description: string
  content_indexed_at: string
  created_by: User | null
  created_at: string
}

// Mirrors `WeeklyActivityBucket`. One bucket per week between the goal's
// activation (or 12 weeks back) and its target (or 4 weeks forward); see
// goal_alignment_show_chart_data in app/helpers/goals.py.
export interface WeeklyActivityBucket {
  week: string
  count: number
}

// Mirrors `TimelineProgressEvent` — snake_case (the API contract). `week_index`
// indexes into weekly_activity.
export interface TimelineProgressEvent {
  week_index: number
  progress: number
}

// Mirrors `TimelineStatusChange`.
export interface TimelineStatusChange {
  week_index: number
  status: string
}

// Mirrors `app.routers.api.goal_alignments.AlignmentTimelineData`. All week math
// (boundaries, today index) is derived server-side; the chart only renders it.
export interface AlignmentTimelineData {
  weekly_activity: WeeklyActivityBucket[]
  progress_events: TimelineProgressEvent[]
  status_changes: TimelineStatusChange[]
  current_progress: number
  current_status: string
  total_weeks: number
  today_week_index: number
  start_date: string
  end_date: string
}

// Mirrors `GoalAlignmentListResponse` — a bounded aggregate (the timeline buckets
// every alignment), so it is not paginated.
export interface GoalAlignmentListResponse {
  alignments: GoalAlignment[]
  timeline: AlignmentTimelineData
}

// Mirrors `AlignableContentResponse` — content candidates from the org-wide
// lookup, slimmer than ContentResponse because the lookup table lacks
// category/preview_content.
export interface AlignableContent {
  id: string
  title: string
  author: string | null
  content_type: string
  source_url: string
}

// Mirrors `AlignableContentListResponse`.
export interface AlignableContentListResponse extends PaginatedResponse {
  results: AlignableContent[]
}
