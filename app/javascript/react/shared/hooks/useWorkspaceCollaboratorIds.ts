import { useMemo } from "react"

import { useWorkspaceCollaboratorsQuery } from "~/react/shared/hooks/useWorkspaceCollaboratorsQuery"

// Collaborator user ids for a workspace, used to flag mention candidates (the "Collaborators /
// Invite to collaborate" split). Derived from the shared, channel-live collaborators query so it
// shares one cached fetch with the collaborators panel and goal timeline, and stays live when
// membership changes mid-session — no bespoke fetch/dedup/subscription of its own.
//
// Returns undefined until loaded — callers treat that as "org-wide, nobody flagged yet", matching
// the old org-wide mention behaviour during the fetch. The query is keyed by workspace id, so a
// workspace switch reads as "loading" for the new id rather than leaking the previous roster.
export function useWorkspaceCollaboratorIds(workspaceId: string | null): Set<string> | undefined {
  const { data } = useWorkspaceCollaboratorsQuery(workspaceId ?? "")
  return useMemo(() => (data ? new Set(data.collaborators.map(c => c.user.id)) : undefined), [data])
}
