// The mount carries no props: the org is resolved server-side from the session,
// and the overview is fetched from GET /api/goal_alignments.
export type GoalAlignmentsIndexProps = Record<string, never>

// Mirrors `app.routers.api.goal_alignments.GoalAlignmentSummary`. snake_case (the
// API contract); the chart reads these keys directly. signal_counts is the
// per-signal breakdown (e.g. {"strong": 2, "medium": 1}); activity is its total.
export interface GoalSummary {
  id: string
  name: string
  description: string | null
  activity: number
  status: string
  group_id: string | null
  group_name: string | null
  url: string
  signal_counts: Record<string, number>
}

// Mirrors `app.routers.api.goal_alignments.GoalAlignmentGroup`.
export interface GoalGroup {
  id: string
  name: string
  goals: GoalSummary[]
}

// Mirrors `app.routers.api.goal_alignments.GoalAlignmentOverviewResponse`: a
// bounded aggregate (every active top-level goal for the org), so it is not
// paginated.
export interface GoalAlignmentOverviewResponse {
  groups: GoalGroup[]
  ungrouped_goals: GoalSummary[]
}
