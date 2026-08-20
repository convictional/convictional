import { queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"

import type { UpdatesConfiguration } from "./types"

// The updates schedule + goal-update question. No channel keeps it live — it
// changes only through this composite's own PATCHes — so it uses standard Query
// defaults and the save handlers patch the cache via setQueryData, mirroring the
// org settings queries (features/organizationSettings/queries.ts).
export const updatesConfigurationQueryOptions = queryOptions({
  queryKey: ["organization", "updates_configuration"] as const,
  queryFn: () => apiFetch<UpdatesConfiguration>("/api/organization/updates_configuration"),
})
