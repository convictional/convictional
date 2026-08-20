import { useState } from "react"

import { EmptyState } from "~/react/ui/EmptyState"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { LoadMoreSentinel } from "~/react/ui/LoadMoreSentinel"
import { GroupCreationRow } from "./components/GroupCreationRow"
import { GroupListRow } from "./components/GroupListRow"
import { GroupsHeader } from "./components/GroupsHeader"
import { useGroupsData } from "./hooks/useGroupsData"

interface GroupsIndexProps {
  canManage: boolean
}

export function GroupsIndex({ canManage }: GroupsIndexProps) {
  const {
    groups,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    canJoin,
    addGroup,
    renameGroup,
    deleteGroup,
    joinGroup,
    leaveGroup,
  } = useGroupsData()

  const [isCreating, setIsCreating] = useState(false)

  const columns = canManage ? "grid-cols-[1fr_200px_120px_auto]" : "grid-cols-[1fr_200px_120px]"

  const sharedProps = {
    canManage,
    canJoin,
    onJoin: joinGroup,
    onLeave: leaveGroup,
    onRename: renameGroup,
    onDelete: deleteGroup,
  }

  if (loading && groups.length === 0) {
    return <LoadingState />
  }

  if (error && groups.length === 0) {
    return <ErrorState message="Failed to load groups. Please try refreshing the page." />
  }

  if (groups.length === 0 && !isCreating) {
    return canManage ? (
      <EmptyState title="No groups yet" text="Create groups to organize your team.">
        <button type="button" className="btn btn-primary" onClick={() => setIsCreating(true)}>
          <span className="material-symbols-outlined text-lg">add</span>
          Create group
        </button>
      </EmptyState>
    ) : (
      <EmptyState title="No groups yet" text="Ask an admin to create a group." />
    )
  }

  return (
    <div>
      {groups.length > 0 && (
        <GroupsHeader canManage={canManage} showCreate={!isCreating} onCreate={() => setIsCreating(true)} />
      )}

      <div className="px-2">
        {isCreating && canManage && (
          <GroupCreationRow
            onCreated={group => {
              addGroup(group)
              setIsCreating(false)
            }}
            onCancel={() => setIsCreating(false)}
          />
        )}

        <div className="rounded-2xl border border-base-300 overflow-hidden">
          <div
            className={`hidden md:grid ${columns} gap-4 px-4 py-3 bg-base-50 border-b border-base-300 text-xs uppercase text-base-content/60 font-semibold`}
          >
            <div>Name</div>
            <div>Members</div>
            <div>&nbsp;</div>
            {canManage && <div className="w-8">&nbsp;</div>}
          </div>
          {groups.map(group => (
            <GroupListRow key={group.id} group={group} {...sharedProps} />
          ))}
        </div>

        {/* On a paging error the sentinel unmounts so the observer stops re-firing;
            recovery is an explicit Retry rather than an unbounded auto-retry loop. */}
        {hasMore && !error && <LoadMoreSentinel onIntersect={loadMore} loading={loadingMore} />}

        {hasMore && error && (
          <div className="flex items-center justify-center py-8">
            <button type="button" className="btn btn-ghost btn-sm" onClick={loadMore}>
              Couldn't load more — Retry
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
