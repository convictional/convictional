import { useEffect, useMemo, useRef, useState } from "react"

import { AvatarGroup } from "~/react/composites/AvatarGroup"
import type { Group, User } from "~/react/shared/types"
import { Dropdown } from "~/react/ui/Dropdown"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { Tooltip } from "~/react/ui/Tooltip"
import type { GoalsView } from "../types"

interface GoalsHeaderProps {
  view: GoalsView
  onChangeView: (view: GoalsView) => void
  planningListNames: string[]
  ownerIds: string[]
  groupIds: string[]
  onToggleOwner: (userId: string) => void
  onToggleGroup: (groupId: string) => void
  onClearFilters: () => void
  orgUsers: User[]
  orgGroups: Group[]
  isPlanningList: boolean
  onStartCreating: () => void
  onActivate: () => void
  goalsCount: number
  presentUsers: User[]
}

function viewLabel(view: GoalsView): string {
  if (view === "active") return "Active"
  if (view === "completed") return "Completed"
  if (view === "closed") return "Closed"
  return view
}

function FilterDropdown({
  view,
  onChangeView,
  planningListNames,
}: {
  view: GoalsView
  onChangeView: (view: GoalsView) => void
  planningListNames: string[]
}) {
  const [creatingPlanningList, setCreatingPlanningList] = useState(false)
  const [newListName, setNewListName] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (creatingPlanningList) inputRef.current?.focus()
  }, [creatingPlanningList])

  return (
    <Dropdown
      placement="bottom-start"
      onOpenChange={open => {
        if (!open) {
          setCreatingPlanningList(false)
          setNewListName("")
        }
      }}
      className="dropdown-card z-50"
      trigger={
        <button type="button" className="btn border border-neutral font-normal text-base-600 flex items-center gap-1">
          {viewLabel(view)}
        </button>
      }
    >
      {({ close }) => {
        const select = (v: GoalsView) => {
          onChangeView(v)
          close()
        }
        const submitNewList = () => {
          const trimmed = newListName.trim()
          if (trimmed) {
            onChangeView(trimmed)
            close()
          }
        }
        const cancelCreating = () => {
          setCreatingPlanningList(false)
          setNewListName("")
        }

        return (
          <>
            <ul className="p-2">
              <li>
                <button className="dropdown-item w-full text-left" onClick={() => select("active")}>
                  Active goals
                </button>
              </li>
              <li>
                <button className="dropdown-item w-full text-left" onClick={() => select("completed")}>
                  Completed goals
                </button>
              </li>
              <li>
                <button className="dropdown-item w-full text-left" onClick={() => select("closed")}>
                  Closed goals
                </button>
              </li>
            </ul>
            {planningListNames.length > 0 && (
              <div className="border-t border-neutral">
                <ul className="p-2">
                  <li className="text-xs pb-2 ml-1 text-base-600/70">Planning Lists</li>
                  {planningListNames.map(name => (
                    <li key={name}>
                      <button className="dropdown-item w-full text-left" onClick={() => select(name)}>
                        {name}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {!creatingPlanningList && (
              <button
                onClick={() => setCreatingPlanningList(true)}
                className="text-xs text-center flex items-center gap-1 justify-center bg-base-100 w-full px-4 py-1 cursor-pointer hover:bg-base-200 hover:text-base-900 transition"
              >
                <span className="material-symbols-outlined text-base">add</span>
                New planning list
              </button>
            )}
            {creatingPlanningList && (
              <div className="p-2">
                <input
                  ref={inputRef}
                  type="text"
                  placeholder="List name"
                  className="input input-sm input-bordered w-full mb-2"
                  value={newListName}
                  onChange={e => setNewListName(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter") submitNewList()
                    if (e.key === "Escape") cancelCreating()
                  }}
                  maxLength={50}
                />
                <div className="flex gap-1 justify-end">
                  <button className="btn btn-sm btn-ghost" onClick={cancelCreating}>
                    Cancel
                  </button>
                  <button className="btn btn-sm btn-primary" disabled={!newListName.trim()} onClick={submitNewList}>
                    Create
                  </button>
                </div>
              </div>
            )}
          </>
        )
      }}
    </Dropdown>
  )
}

function TeamFilter({
  ownerIds,
  groupIds,
  onToggleOwner,
  onToggleGroup,
  onClearFilters,
  orgUsers,
  orgGroups,
}: {
  ownerIds: string[]
  groupIds: string[]
  onToggleOwner: (userId: string) => void
  onToggleGroup: (groupId: string) => void
  onClearFilters: () => void
  orgUsers: User[]
  orgGroups: Group[]
}) {
  const [search, setSearch] = useState("")
  const filterCount = ownerIds.length + groupIds.length

  const searchLower = search.toLowerCase()
  const filteredUsers = useMemo(
    () => orgUsers.filter(u => u.display_name.toLowerCase().includes(searchLower)),
    [orgUsers, searchLower]
  )
  const filteredGroups = useMemo(
    () => orgGroups.filter(g => g.name.toLowerCase().includes(searchLower)),
    [orgGroups, searchLower]
  )

  return (
    <Dropdown
      placement="bottom-start"
      onOpenChange={open => !open && setSearch("")}
      className="z-50 dropdown-card w-64"
      trigger={
        <button type="button" className="btn border border-neutral font-normal text-base-600 flex items-center gap-1">
          <span>Team</span>
          {filterCount > 0 ? (
            <span className="bg-primary text-primary-content text-[10px] font-bold rounded-full min-w-4 h-4 flex items-center justify-center px-1">
              {filterCount}
            </span>
          ) : (
            <span className="material-symbols-outlined text-sm">arrow_drop_down</span>
          )}
        </button>
      }
    >
      <>
        <div className="p-2">
          <input
            type="text"
            placeholder="Search..."
            className="input input-sm input-bordered !outline-none bg-base-50 w-full"
            value={search}
            onChange={e => setSearch(e.target.value)}
            autoFocus
          />
        </div>
        {filteredUsers.length > 0 && (
          <div className="p-2 pt-0">
            <span className="text-xs font-semibold opacity-75 px-1">People</span>
            <ul className="max-h-40 overflow-y-auto grid gap-0.5 mt-1">
              {filteredUsers.map(user => (
                <li key={user.id}>
                  <button
                    className="dropdown-item p-1 w-full flex items-center gap-2"
                    onClick={() => onToggleOwner(user.id)}
                  >
                    <span
                      className={`material-symbols-outlined text-sm ${ownerIds.includes(user.id) ? "text-primary" : "text-base-content/30"}`}
                    >
                      {ownerIds.includes(user.id) ? "check_box" : "check_box_outline_blank"}
                    </span>
                    <span className="text-xs font-semibold truncate">{user.display_name}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {filteredGroups.length > 0 && (
          <div className="p-2 pt-0">
            <span className="text-xs font-semibold opacity-75 px-1">Groups</span>
            <ul className="max-h-40 overflow-y-auto grid gap-0.5 mt-1">
              {filteredGroups.map(group => (
                <li key={group.id}>
                  <button
                    className="dropdown-item p-1 w-full flex items-center gap-2"
                    onClick={() => onToggleGroup(group.id)}
                  >
                    <span
                      className={`material-symbols-outlined text-sm ${groupIds.includes(group.id) ? "text-primary" : "text-base-content/30"}`}
                    >
                      {groupIds.includes(group.id) ? "check_box" : "check_box_outline_blank"}
                    </span>
                    <span className="text-xs font-semibold truncate">{group.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {filterCount > 0 && (
          <button
            onClick={onClearFilters}
            className="text-xs text-center flex items-center gap-1 justify-center bg-base-100 w-full px-4 py-1 cursor-pointer hover:bg-base-200 hover:text-base-900 transition"
          >
            <span className="material-symbols-outlined text-base">filter_alt_off</span>
            Clear filters
          </button>
        )}
      </>
    </Dropdown>
  )
}

export function GoalsHeader({
  view,
  onChangeView,
  planningListNames,
  ownerIds,
  groupIds,
  onToggleOwner,
  onToggleGroup,
  onClearFilters,
  orgUsers,
  orgGroups,
  isPlanningList,
  onStartCreating,
  onActivate,
  goalsCount,
  presentUsers,
}: GoalsHeaderProps) {
  return (
    <StickyHeader>
      <div className="flex items-center justify-between gap-2 p-2">
        <div className="flex items-center gap-2">
          <FilterDropdown view={view} onChangeView={onChangeView} planningListNames={planningListNames} />
          <TeamFilter
            ownerIds={ownerIds}
            groupIds={groupIds}
            onToggleOwner={onToggleOwner}
            onToggleGroup={onToggleGroup}
            onClearFilters={onClearFilters}
            orgUsers={orgUsers}
            orgGroups={orgGroups}
          />
        </div>
        <div className="flex items-center gap-2">
          <AvatarGroup layout="stack" users={presentUsers} presentUserIds={presentUsers.map(u => u.id)} max={5} />
          {isPlanningList ? (
            <button onClick={onActivate} className="btn btn-primary" disabled={goalsCount === 0}>
              Activate goals
            </button>
          ) : (
            <Tooltip content="Create goal">
              <button onClick={onStartCreating} className="btn btn-square">
                <span className="material-symbols-outlined text-base">add</span>
              </button>
            </Tooltip>
          )}
        </div>
      </div>
    </StickyHeader>
  )
}
