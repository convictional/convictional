// Shared lookup-search client used by the command palette (desktop) and the
// mobile search overlay. Mirrors response shapes from /api/commands/* — see
// app/routers/api/commands.py.

import { apiFetch } from "~/react/shared/apiFetch"

export interface LookupResult {
  id: string
  content_type: string
  title: string
  url: string
  updated_at: string
  display_at: string
  authors: string[]
  preview: string | null
  shared_with_me: boolean
  email: string | null
  avatar_url: string | null
  global_id: string
}

export interface LookupResults {
  user_results: LookupResult[]
  other_results: LookupResult[]
}

export interface FilterMeta {
  kind: "user" | "contact"
  id: string
  name: string
  email: string | null
  avatar_url: string | null
  global_id: string
}

export interface LookupResponse {
  results: LookupResults
  query: string
}

export interface PeopleResponse {
  results: LookupResults
  query: string
  filter: FilterMeta | null
}

export interface TrackPayload {
  query: string
  result_count: number
  result_ids: string[]
  clicked_content_id?: string
  clicked_position?: number
  filter_author_gid?: string | null
}

export function fetchLookup(query: string, signal?: AbortSignal): Promise<LookupResponse> {
  const params = new URLSearchParams({ query })
  return apiFetch<LookupResponse>(`/api/commands/lookup?${params}`, { signal })
}

export function fetchPeople(authorGid: string, query: string, signal?: AbortSignal): Promise<PeopleResponse> {
  const params = new URLSearchParams({ author_gid: authorGid })
  if (query) params.set("query", query)
  return apiFetch<PeopleResponse>(`/api/commands/people?${params}`, { signal })
}

// Tracking is fire-and-forget — failures must never surface in the UI.
export function trackSearch(payload: TrackPayload): void {
  apiFetch("/api/commands/lookup/track", {
    method: "POST",
    body: JSON.stringify(payload),
  }).catch(() => {})
}
