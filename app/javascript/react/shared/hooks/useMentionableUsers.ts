import { useMemo } from "react"

import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"

export interface MentionUser {
  id: string
  display_name: string
  is_collaborator: boolean
}

interface MentionableOptions {
  // Workspace collaborator ids. Empty/undefined reproduces the old org-wide
  // `available` behaviour: everyone mentionable, nobody flagged.
  collaboratorIds?: Set<string>
  // Skip loading the org roster when the editor has mentions disabled, so a
  // mentions-less editor doesn't fetch members or arm the org-members channel.
  enabled?: boolean
}

// Derives mention candidates from the shared organizationMembers store, flagging
// workspace collaborators client-side. Replaces the three hand-rolled mention
// endpoints. Callers that want collaborators only (chat) filter on
// `is_collaborator` themselves. The current user is included — mentioning
// yourself works just like mentioning anyone else and notifies you the same way.
export function useMentionableUsers({ collaboratorIds, enabled = true }: MentionableOptions = {}): MentionUser[] {
  const { users } = useOrganizationMembers({ enabled })
  return useMemo(
    () =>
      users.map(u => ({
        id: u.id,
        display_name: u.display_name,
        is_collaborator: collaboratorIds?.has(u.id) ?? false,
      })),
    [users, collaboratorIds]
  )
}
