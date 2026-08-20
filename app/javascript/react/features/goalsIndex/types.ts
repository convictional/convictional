import type { PaginatedResponse, Goal } from "~/react/shared/types"

export interface GoalListResponse extends PaginatedResponse {
  goals: Goal[]
  planning_list_names: string[] | null
}

// (string & {}) preserves autocomplete for known values while allowing dynamic planning list names
export type GoalsView = "active" | "completed" | "closed" | (string & {})
