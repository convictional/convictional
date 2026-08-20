import type { GoalSummary } from "../types"

// The parent flattens groups before passing goals here, interleaving each group's
// goals, so we re-sort by name to present a single alphabetical list. This ignores
// incoming order — if the server ever adopts a deliberate ordering (e.g. pinned
// goals first), drop this sort.
export function GoalList({ goals }: { goals: GoalSummary[] }) {
  const sorted = [...goals].sort((a, b) => a.name.localeCompare(b.name))

  return (
    <div className="flex flex-col gap-2">
      {sorted.map(goal => {
        const strong = goal.signal_counts.strong ?? 0
        const medium = goal.signal_counts.medium ?? 0

        return (
          <a
            key={goal.id}
            href={goal.url}
            className="card card-compact bg-base-200 hover:bg-base-300 transition cursor-pointer"
          >
            <div className="card-body px-4 py-3 flex-row items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <div className="flex flex-col gap-1">
                  <span className="text-sm font-medium truncate">{goal.name}</span>
                  <span className="text-xs text-base-500 truncate">{goal.description}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {strong > 0 && <span className="badge badge-sm badge-success">{strong} strong</span>}
                {medium > 0 && <span className="badge badge-sm badge-warning">{medium} medium</span>}
                {strong === 0 && medium === 0 && <span className="badge badge-sm badge-ghost">No alignments</span>}
              </div>
            </div>
          </a>
        )
      })}
    </div>
  )
}
