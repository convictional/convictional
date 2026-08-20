import { useState } from "react"

import { AvatarGroup } from "~/react/composites/AvatarGroup"
import type { GroupRow } from "~/react/features/groupsIndex/types"
import { GroupRowActions } from "./GroupRowActions"

interface GroupListRowProps {
  group: GroupRow
  canManage: boolean
  canJoin: boolean
  onJoin: (id: string) => void
  onLeave: (id: string) => void
  onRename: (id: string, name: string) => void
  onDelete: (id: string) => void
}

export function GroupListRow({ group, canManage, canJoin, onJoin, onLeave, onRename, onDelete }: GroupListRowProps) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(group.name)

  const columns = canManage
    ? "grid-cols-[1fr_auto_auto] md:grid-cols-[1fr_200px_120px_auto]"
    : "grid-cols-[1fr_auto_auto] md:grid-cols-[1fr_200px_120px]"

  function submitRename(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    if (trimmed !== group.name) onRename(group.id, trimmed)
    setEditing(false)
  }

  if (editing) {
    return (
      <div
        className={`grid ${columns} gap-2 md:gap-4 px-4 py-3 items-center bg-base-50 border-b border-base-300 last:border-b-0`}
      >
        <form className="flex gap-2 items-center col-span-full" onSubmit={submitRename}>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Escape") {
                setName(group.name)
                setEditing(false)
              }
            }}
            className="input input-sm bg-base-100 flex-1"
            required
            autoFocus
          />
          <button type="submit" className="btn btn-sm btn-primary">
            Save
          </button>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => {
              setName(group.name)
              setEditing(false)
            }}
          >
            Cancel
          </button>
        </form>
      </div>
    )
  }

  return (
    <div
      className={`grid ${columns} gap-2 md:gap-4 px-4 py-3 items-center bg-base-50 border-b border-base-300 last:border-b-0 group/row`}
    >
      <div className="min-w-0 col-span-3 md:col-span-1">
        <div className="text-sm truncate">{group.name}</div>
      </div>
      <div className="flex items-center">
        <AvatarGroup
          users={group.members.map(m => m.user)}
          layout="stack"
          size="small"
          max={5}
          emptyState={<span className="text-sm text-base-500">None</span>}
        />
      </div>
      <div className="flex justify-end">
        {group.is_member ? (
          <button type="button" className="btn btn-ghost btn-sm" disabled={!canJoin} onClick={() => onLeave(group.id)}>
            Leave
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!canJoin}
            onClick={() => onJoin(group.id)}
          >
            Join
          </button>
        )}
      </div>
      {canManage && (
        <div className="w-8 flex justify-center">
          <GroupRowActions
            groupName={group.name}
            onEdit={() => setEditing(true)}
            onDelete={() => onDelete(group.id)}
            triggerClassName="btn btn-ghost btn-sm btn-circle md:opacity-0 md:group-hover/row:opacity-100"
          />
        </div>
      )}
    </div>
  )
}
