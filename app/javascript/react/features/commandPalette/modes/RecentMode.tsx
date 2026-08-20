import { RecentRow } from "../results/RecentRow"
import type { RecentItem } from "../types"

interface RecentModeProps {
  items: RecentItem[]
  selectedIndex: number
  onSelect: (index: number) => void
  onActivate: () => void
}

export function RecentMode({ items, selectedIndex, onSelect, onActivate }: RecentModeProps) {
  return (
    <div className="p-2 grid gap-3 overflow-y-auto max-h-[calc(100dvh-180px)]">
      <p className="text-xs text-base-500 px-2">Recent</p>
      {items.length === 0 ? (
        <p className="text-center text-sm text-base-500 py-8">No recent items</p>
      ) : (
        <ul className="divide-y divide-base-300 border border-base-300 rounded-2xl overflow-hidden shadow-xs mx-2">
          {items.map((visit, index) => (
            <RecentRow
              key={visit.workspace_id}
              visit={visit}
              isSelected={selectedIndex === index}
              onHover={() => onSelect(index)}
              onActivate={onActivate}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
