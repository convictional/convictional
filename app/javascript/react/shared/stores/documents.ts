import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { backNavigation } from "~/react/shared/backNavigation"
import { queryClient } from "~/react/shared/queryClient"
import type {
  BackNavigation,
  DocumentContentResponse,
  DocumentFilter,
  DocumentListResponse,
  DocumentShowResponse,
} from "~/react/shared/types"

// Server state for documents, fetched through TanStack Query. Shared (not
// per-feature) because both documentShow and documentEditor read the detail
// query, and features are sealed from each other.
//
// Posture: STANDARD Query defaults — deliberately NOT channelQueryDefaults.
// None of these reads is kept live by a metadata WebSocket channel (title and
// sharing change through the editor's own PATCH; content lives in Yjs). With no
// channel to invalidate on, a channel-first query (staleTime: Infinity,
// refetchOnMount: false) would serve indefinitely stale data and never recover.
// So we keep TanStack's defaults — refetch on mount/reconnect — and invalidate
// explicitly from the mutations that change a document.

const DEFAULT_FILTER: DocumentFilter = "mine"

function listUrl(filter: DocumentFilter, cursor: string | null): string {
  const params = new URLSearchParams()
  if (filter !== DEFAULT_FILTER) params.set("filter", filter)
  if (cursor) params.set("cursor", cursor)
  const qs = params.toString()
  return `/api/documents${qs ? `?${qs}` : ""}`
}

// The browse list — cursor pagination over GET /api/documents, keyed by filter.
// getNextPageParam reads next_cursor from the DocumentListResponse envelope.
export function documentsListQueryOptions(filter: DocumentFilter) {
  return infiniteQueryOptions({
    queryKey: ["documents", { filter }] as const,
    queryFn: ({ pageParam, signal }) => apiFetch<DocumentListResponse>(listUrl(filter, pageParam), { signal }),
    initialPageParam: null as string | null,
    getNextPageParam: lastPage => (lastPage.has_more ? lastPage.next_cursor : undefined),
  })
}

// 403 is control flow, not a failure: a viewer who can't access the document
// gets a 403 carrying request_access_url (see request_access_handler), which the
// show page turns into a "request access" affordance. Declaring it expected
// keeps it out of Sentry while apiFetch still throws so the query surfaces it.
const ACCESS_DENIED: { expectedStatuses: number[] } = { expectedStatuses: [403] }

// The detail query — GET /api/documents/{id} → DocumentShowResponse. Warmed by
// the show page and reused by the editor header.
export function documentQueryOptions(documentId: string) {
  return queryOptions({
    queryKey: ["document", documentId] as const,
    queryFn: ({ signal }) => apiFetch<DocumentShowResponse>(`/api/documents/${documentId}`, { signal }, ACCESS_DENIED),
  })
}

// The rendered-markdown sub-resource — GET /api/documents/{id}/content. Used by
// the read-only show page (collaborators consume content over Yjs instead).
export function documentContentQueryOptions(documentId: string) {
  return queryOptions({
    queryKey: ["document", documentId, "content"] as const,
    queryFn: ({ signal }) =>
      apiFetch<DocumentContentResponse>(`/api/documents/${documentId}/content`, { signal }, ACCESS_DENIED),
  })
}

// Invalidate every cached representation of one document (detail + content),
// for callers that mutate a document and need its views to refetch.
export function invalidateDocument(documentId: string): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: ["document", documentId] })
}

// The "back" target for a document view. The documents index is the fallback
// when the document wasn't reached from a labeled origin. The return_to → label
// rule itself lives in backNavigation (shared). Shared here so the show page and
// the editor label Back identically.
export function documentBackNavigation(returnTo: string | undefined): BackNavigation {
  return backNavigation(returnTo, { url: "/documents", label: "Back to documents" })
}
