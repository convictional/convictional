import { useState } from "react"

import type { GoalOption } from "../types"

function GoalPickerGroup({ label }: { label: string }) {
  return <p className="px-2 pb-0.5 pt-1.5 text-[11px] font-semibold text-base-600">{label}</p>
}

function GoalOptionButton({
  goal,
  selected,
  onChoose,
}: {
  goal: GoalOption
  selected: boolean
  onChoose: () => void
}) {
  return (
    <button
      type="button"
      className="dropdown-item flex w-full items-center justify-between gap-2 text-left text-xs"
      onClick={onChoose}
    >
      <span className="truncate">{goal.title}</span>
      {selected && <span className="material-symbols-outlined shrink-0 text-sm text-primary">check</span>}
    </button>
  )
}

function GoalSection({
  label,
  goals,
  selectedId,
  onSelect,
}: {
  label: string
  goals: GoalOption[]
  selectedId: string | null
  onSelect: (goalId: string) => void
}) {
  return (
    <>
      <GoalPickerGroup label={label} />
      {goals.map(goal => (
        <GoalOptionButton
          key={goal.id}
          goal={goal}
          selected={goal.id === selectedId}
          onChoose={() => onSelect(goal.id)}
        />
      ))}
    </>
  )
}

// Split the goals the user is most likely to want into labeled sections, mirroring the mock:
// goals owned by the user ("Assigned to me"), then a section per group the user belongs to,
// then everything else ("Other goals"). An owned goal appears only under "Assigned to me"; goals
// in groups the user isn't a member of fall to "Other goals". The split applies to the filtered
// results too, so the sections hold their shape while searching.
//
// The full goal set is loaded up front (FocusDropdown follows the /api/goals cursor across all
// pages), so the sections and the typeahead search cover every goal client-side.
export function sectionGoals(goals: GoalOption[], currentUserId: string | null, myGroupIds: string[]) {
  const myGroups = new Set(myGroupIds)
  const mine = currentUserId ? goals.filter(g => g.ownerId === currentUserId) : []
  const rest = currentUserId ? goals.filter(g => g.ownerId !== currentUserId) : goals

  const goalsByGroup = new Map<string, GoalOption[]>()
  for (const goal of rest) {
    if (goal.groupId && myGroups.has(goal.groupId)) {
      const bucket = goalsByGroup.get(goal.groupId)
      if (bucket) bucket.push(goal)
      else goalsByGroup.set(goal.groupId, [goal])
    }
  }
  // Preserve the order /api/groups returned; a group with no loaded goals gets no section.
  const groupSections = myGroupIds
    .map(id => ({ id, goals: goalsByGroup.get(id) }))
    .filter((section): section is { id: string; goals: GoalOption[] } => !!section.goals && section.goals.length > 0)
    .map(section => ({ id: section.id, name: section.goals[0].groupName ?? "Group", goals: section.goals }))

  const others = rest.filter(g => !(g.groupId && myGroups.has(g.groupId)))
  return { mine, groupSections, others }
}

// Goal picker overlay for the "By goal" sort: typeahead search over the loaded goals, sectioned by
// `sectionGoals` so the user's own and group goals surface first.
export function GoalPicker({
  goals,
  loading,
  selectedId,
  currentUserId,
  myGroupIds,
  onSelect,
}: {
  goals: GoalOption[]
  loading: boolean
  selectedId: string | null
  currentUserId: string | null
  myGroupIds: string[]
  onSelect: (goalId: string) => void
}) {
  const [query, setQuery] = useState("")
  const trimmed = query.trim().toLowerCase()
  const matches = trimmed ? goals.filter(g => g.title.toLowerCase().includes(trimmed)) : goals
  const { mine, groupSections, others } = sectionGoals(matches, currentUserId, myGroupIds)
  // A lone "Other goals" header reads as noise when there's nothing above it, so render the
  // remainder flat (no header) unless an "Assigned to me" or group section precedes it.
  const hasSectionsAbove = mine.length > 0 || groupSections.length > 0

  return (
    <div className="flex flex-col gap-3 p-4">
      <h2 className="text-base font-semibold text-base-content">Sort by goal</h2>
      <div className="relative">
        <span className="material-symbols-outlined pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-base text-base-500">
          search
        </span>
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search goals…"
          autoFocus
          className="w-full rounded-lg border border-base-400/70 bg-base-100 py-2 pl-9 pr-3 text-sm placeholder:text-base-content/40 focus:border-primary/50 focus:outline-hidden focus:ring-2 focus:ring-primary/20"
        />
      </div>
      <div className="-mx-1 max-h-72 overflow-y-auto overscroll-contain px-1 [scrollbar-width:thin]">
        {loading ? (
          <p className="px-2 py-2 text-xs text-base-content/50">Loading goals…</p>
        ) : matches.length > 0 ? (
          <>
            {mine.length > 0 && (
              <GoalSection label="Assigned to me" goals={mine} selectedId={selectedId} onSelect={onSelect} />
            )}
            {groupSections.map(section => (
              <GoalSection
                key={section.id}
                label={section.name}
                goals={section.goals}
                selectedId={selectedId}
                onSelect={onSelect}
              />
            ))}
            {others.length > 0 &&
              (hasSectionsAbove ? (
                <GoalSection label="Other goals" goals={others} selectedId={selectedId} onSelect={onSelect} />
              ) : (
                others.map(goal => (
                  <GoalOptionButton
                    key={goal.id}
                    goal={goal}
                    selected={goal.id === selectedId}
                    onChoose={() => onSelect(goal.id)}
                  />
                ))
              ))}
          </>
        ) : (
          <p className="px-2 py-2 text-xs text-base-content/50">
            {trimmed ? `No goals match “${query.trim()}”` : "No goals yet"}
          </p>
        )}
      </div>
    </div>
  )
}
