import type { DocumentFilter } from "~/react/features/documentsIndex/types"
import { Dropdown } from "~/react/ui/Dropdown"

const LABELS: Record<DocumentFilter, string> = {
  mine: "Owned by me",
  others: "Owned by others",
  anyone: "Owned by anyone",
}

interface FilterDropdownProps {
  filter: DocumentFilter
  onChange: (filter: DocumentFilter) => void
}

export function FilterDropdown({ filter, onChange }: FilterDropdownProps) {
  return (
    <Dropdown
      placement="bottom-start"
      className="dropdown-card p-2 z-50"
      trigger={
        <button type="button" className="btn border border-neutral font-normal text-base-600 flex items-center gap-1">
          {LABELS[filter]}
        </button>
      }
    >
      {({ close }) => (
        <ul>
          {(Object.keys(LABELS) as DocumentFilter[]).map(value => (
            <li key={value}>
              <button
                type="button"
                className="dropdown-item text-xs w-full text-left"
                onClick={() => {
                  onChange(value)
                  close()
                }}
              >
                <span>{LABELS[value]}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Dropdown>
  )
}
