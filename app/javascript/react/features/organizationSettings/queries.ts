import { queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"

import type { OrganizationData } from "./types"

// Settings-page server state. The org name / system prompt has no metadata channel
// keeping it live — it changes only through this page's own actions — so it uses
// standard Query defaults (stale on arrival, refetch on mount) and the Basics /
// System Prompt mutations invalidate the org key explicitly, rather than the
// channel-first posture in channelQueryDefaults.

export const organizationQueryOptions = queryOptions({
  queryKey: ["organization"] as const,
  queryFn: () => apiFetch<OrganizationData>("/api/organization"),
})
