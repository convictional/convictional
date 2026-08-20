import { useCallback, useEffect, useRef } from "react"

import type { GroupListResponse, GroupMemberAvatar, GroupRow } from "~/react/features/groupsIndex/types"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { usePaginatedList } from "~/react/shared/hooks/usePaginatedList"
import { showFlash } from "~/shared/flash"

// A 409 on join/leave means the desired end state already holds (a second tab
// or a stale card raced the mutation). Reconcile to that state and suppress the
// error flash rather than showing a spurious failure.
function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409
}

export function useGroupsData() {
  const { user: currentUser } = useCurrentUser()

  const {
    items: groups,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    setItems: setGroups,
  } = usePaginatedList<GroupRow, GroupListResponse>({
    buildUrl: cursor => (cursor ? `/api/groups?cursor=${encodeURIComponent(cursor)}` : "/api/groups"),
    select: data => data.groups,
  })

  // Mirror groups into a ref so the optimistic mutations (which run in async
  // event handlers, after commit) can snapshot the current list for rollback.
  const groupsRef = useRef(groups)
  useEffect(() => {
    groupsRef.current = groups
  }, [groups])

  const updateGroup = useCallback(
    (id: string, updater: (group: GroupRow) => GroupRow) => {
      setGroups(prev => prev.map(g => (g.id === id ? updater(g) : g)))
    },
    [setGroups]
  )

  // Newly created groups appear at the top so they're visible right where the
  // creation row sits. loadMore dedupes by id if a later page includes it.
  const addGroup = useCallback(
    (group: GroupRow) => {
      setGroups(prev => (prev.some(g => g.id === group.id) ? prev : [group, ...prev]))
    },
    [setGroups]
  )

  const renameGroup = useCallback(
    (id: string, name: string) => {
      const previous = groupsRef.current.find(g => g.id === id)
      if (!previous) return

      updateGroup(id, g => ({ ...g, name }))
      apiFetch<GroupRow>(`/api/groups/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      })
        .then(updated => updateGroup(id, () => updated))
        .catch(() => {
          updateGroup(id, g => ({ ...g, name: previous.name }))
          showFlash("Couldn't rename the group.")
        })
    },
    [updateGroup]
  )

  const deleteGroup = useCallback(
    (id: string) => {
      const list = groupsRef.current
      const index = list.findIndex(g => g.id === id)
      if (index === -1) return
      const removed = list[index]

      setGroups(prev => prev.filter(g => g.id !== id))
      apiFetch(`/api/groups/${id}`, { method: "DELETE" }).catch(() => {
        // Re-insert only the deleted row near its old slot, so concurrent
        // optimistic edits to other rows aren't clobbered by a whole-list restore.
        setGroups(prev => {
          if (prev.some(g => g.id === id)) return prev
          const next = [...prev]
          next.splice(Math.min(index, next.length), 0, removed)
          return next
        })
        showFlash("Couldn't delete the group.")
      })
    },
    [setGroups]
  )

  const joinGroup = useCallback(
    (id: string) => {
      if (!currentUser) return
      const me = currentUser
      const previous = groupsRef.current.find(g => g.id === id)
      if (!previous || previous.is_member) return

      // member.id is a GroupMember record UUID, which we don't have yet. Use a
      // sentinel so nothing mistakes the user's id for a membership-record id;
      // the server's canonical record replaces it on reconcile below.
      const optimisticId = `optimistic-${me.id}`
      const optimisticMember = {
        id: optimisticId,
        user: { id: me.id, display_name: me.display_name, picture: me.picture },
      }
      updateGroup(id, g => ({
        ...g,
        is_member: true,
        members: [...g.members, optimisticMember],
        member_count: g.member_count + 1,
      }))

      apiFetch<GroupMemberAvatar>(`/api/groups/${id}/members`, {
        method: "POST",
        body: JSON.stringify({ user_id: me.id }),
      })
        // Reconcile the optimistic member with the server's canonical record.
        .then(member =>
          updateGroup(id, g => ({ ...g, members: g.members.map(m => (m.id === optimisticId ? member : m)) }))
        )
        .catch(e => {
          if (isConflict(e)) return
          updateGroup(id, g => ({
            ...g,
            is_member: false,
            members: g.members.filter(m => m.user.id !== me.id),
            member_count: Math.max(g.member_count - 1, 0),
          }))
          showFlash("Couldn't join the group.")
        })
    },
    [currentUser, updateGroup]
  )

  const leaveGroup = useCallback(
    (id: string) => {
      if (!currentUser) return
      const me = currentUser
      const previous = groupsRef.current.find(g => g.id === id)
      if (!previous || !previous.is_member) return

      updateGroup(id, g => ({
        ...g,
        is_member: false,
        members: g.members.filter(m => m.user.id !== me.id),
        member_count: Math.max(g.member_count - 1, 0),
      }))

      apiFetch(`/api/groups/${id}/members/${me.id}`, { method: "DELETE" }).catch(e => {
        if (isConflict(e)) return
        updateGroup(id, () => previous)
        showFlash("Couldn't leave the group.")
      })
    },
    [currentUser, updateGroup]
  )

  return {
    groups,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    canJoin: !!currentUser,
    addGroup,
    renameGroup,
    deleteGroup,
    joinGroup,
    leaveGroup,
  }
}
