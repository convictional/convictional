import { apiFetch } from "~/react/shared/apiFetch"
import {
  fetchLookup,
  fetchPeople,
  trackSearch,
  type LookupResponse,
  type PeopleResponse,
  type TrackPayload,
} from "~/react/shared/lookup"
import type { PaginatedResponse } from "~/react/shared/types"

import type { Command, QuickLink, RecentItem, ResearchQuestion } from "./types"

export type { LookupResponse, PeopleResponse, TrackPayload }
export { fetchLookup, fetchPeople, trackSearch }

export interface RecentResponse extends PaginatedResponse {
  recent_items: RecentItem[]
}

export interface CommandsResponse extends PaginatedResponse {
  commands: Command[]
}

export function fetchRecent(signal?: AbortSignal): Promise<RecentResponse> {
  return apiFetch<RecentResponse>("/api/commands/recent", { signal })
}

export function fetchCommands(signal?: AbortSignal): Promise<CommandsResponse> {
  return apiFetch<CommandsResponse>("/api/commands", { signal })
}

export function fetchQuickLink(id: string, signal?: AbortSignal): Promise<QuickLink> {
  return apiFetch<QuickLink>(`/api/quick_links/${id}`, { signal })
}

export interface QuickLinkPayload {
  label: string
  url: string
  open_in_new_tab: boolean
}

export function createQuickLink(payload: QuickLinkPayload): Promise<QuickLink> {
  return apiFetch<QuickLink>("/api/quick_links", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateQuickLink(id: string, payload: QuickLinkPayload): Promise<QuickLink> {
  return apiFetch<QuickLink>(`/api/quick_links/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

export function deleteQuickLink(id: string): Promise<null> {
  return apiFetch<null>(`/api/quick_links/${id}`, { method: "DELETE" })
}

export function createResearchQuestion(body: string): Promise<ResearchQuestion> {
  return apiFetch<ResearchQuestion>("/api/research_questions", {
    method: "POST",
    body: JSON.stringify({ body }),
  })
}
