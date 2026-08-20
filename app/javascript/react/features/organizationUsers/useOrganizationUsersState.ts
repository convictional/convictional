import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { ChannelEventResource, ChannelStream } from "~/types/channels"

import type { OrganizationUser, OrganizationUsersListResponse } from "./types"

interface State {
  users: OrganizationUser[] | null
  loading: boolean
  error: boolean
  // Applies the server's response for a single member (from an invite POST or a
  // PATCH) into the list. Mutations use this instead of a refetch, so the acting
  // session updates instantly and the PATCH/POST response isn't thrown away.
  upsertUser: (user: OrganizationUser) => void
}

// Match the server ordering (api/organization.py: `sorted(key=(is_deleted, email))`):
// active members first, then by email. Python compares strings by codepoint, so we
// compare raw (not localeCompare, whose case-folding would reorder mixed-case emails
// differently than the server) — keeping a local upsert in the same order a refetch
// would produce.
function sortMembers(members: OrganizationUser[]): OrganizationUser[] {
  return [...members].sort((a, b) => {
    if (a.active !== b.active) return a.active ? -1 : 1
    return a.email < b.email ? -1 : a.email > b.email ? 1 : 0
  })
}

// Loads the admin member list from GET /api/organization/users and keeps it
// live. Membership changes (a deactivate/restore here or in another tab, group
// edits elsewhere) fan out as an ORGANIZATION_MEMBERS event on the topic in the
// list payload, which every subscriber — including the acting session, the
// broadcast isn't sender-excluded — answers with a full refetch. The acting
// session also patches its own mutation result in immediately via upsertUser for
// instant feedback; the trailing reconcile keeps local and server state aligned.
export function useOrganizationUsersState(): State {
  const [users, setUsers] = useState<OrganizationUser[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const loadedRef = useRef(false)
  const organizationId = useCurrentUser().user?.organization_id ?? null

  const refetch = useCallback(async () => {
    try {
      const data = await apiFetch<OrganizationUsersListResponse>("/api/organization/users")
      loadedRef.current = true
      setUsers(sortMembers(data.users))
      setError(false)
    } catch {
      // Once the list is on screen, a failed background refetch (a channel-driven
      // reconcile, or a transient blip) must not wipe it — keep the stale data
      // and recover on the next successful refetch. Only a failed initial load
      // surfaces the error state.
      if (!loadedRef.current) setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  const upsertUser = useCallback((user: OrganizationUser) => {
    setUsers(prev => {
      const base = prev ?? []
      const next = base.some(u => u.id === user.id) ? base.map(u => (u.id === user.id ? user : u)) : [...base, user]
      return sortMembers(next)
    })
  }, [])

  useEffect(() => {
    void refetch()
  }, [refetch])

  useChannel(
    organizationId
      ? { stream: ChannelStream.ORGANIZATION_MEMBERS, params: { organization_id: organizationId } }
      : null,
    ChannelEventResource.ORGANIZATION_MEMBERS,
    () => {
      void refetch()
    }
  )

  return { users, loading, error, upsertUser }
}
