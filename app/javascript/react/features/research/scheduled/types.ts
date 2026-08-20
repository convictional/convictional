// Mirrors Pydantic response shapes in app/routers/api/scheduled_research.py and the
// ScheduledResearchFrequency enum in config/enums.py.

import type { PaginatedResponse } from "~/react/shared/types"

export enum ScheduledResearchFrequency {
  DAILY = "daily",
  WEEKLY = "weekly",
  WEEKDAYS = "weekdays",
}

export interface ScheduledResearch {
  id: string
  title: string
  prompt: string
  frequency: ScheduledResearchFrequency
  hour: number
  day_of_week: string | null
  schedule_description: string
  next_run_at: string | null
  last_delivered_at: string | null
  preparation_failed_at: string | null
  created_at: string
}

export interface ScheduledResearchListResponse extends PaginatedResponse {
  scheduled_researches: ScheduledResearch[]
}

export interface ScheduledResearchPrefillResponse {
  prompt: string
}

export interface ScheduledResearchPreviewResponse {
  preview_id: string
  expires_at: string
}

export interface ScheduledResearchCreateRequest {
  prompt: string
  frequency: ScheduledResearchFrequency
  hour: number
  day_of_week?: string | null
}

export type ScheduledResearchUpdateRequest = Partial<ScheduledResearchCreateRequest>
