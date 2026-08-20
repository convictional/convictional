import { Avatar } from "~/react/ui/Avatar"
import type { FilterMeta } from "./types"

interface FilterChipProps {
  filter: FilterMeta
  onClear: () => void
}

export function FilterChip({ filter, onClear }: FilterChipProps) {
  return (
    <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-primary/10 text-primary text-sm shrink-0">
      {filter.kind === "user" ? (
        <Avatar displayName={filter.name} picture={filter.avatar_url} size="small" />
      ) : (
        <span className="material-symbols-outlined text-sm">contact_mail</span>
      )}
      <span>{filter.name}</span>
      <button
        type="button"
        onClick={onClear}
        className="ml-1 hover:bg-primary/20 rounded p-0.5 transition-colors"
        aria-label="Clear filter"
      >
        <span className="material-symbols-outlined text-sm">close</span>
      </button>
    </div>
  )
}
