import { Dropdown } from "~/react/ui/Dropdown"
import { CONTENT_TYPE_FILTERS, type ContentTypeFilter as ContentTypeFilterValue } from "../types"

interface ContentTypeFilterProps {
  activeType: ContentTypeFilterValue | null
  onChange: (type: ContentTypeFilterValue | null) => void
}

function activeLabel(activeType: ContentTypeFilterValue | null): string {
  return CONTENT_TYPE_FILTERS.find(f => f.value === activeType)?.label ?? "All"
}

export function ContentTypeFilter({ activeType, onChange }: ContentTypeFilterProps) {
  return (
    <Dropdown
      placement="bottom-start"
      className="dropdown-card p-2 z-50"
      trigger={
        <button type="button" className="btn btn-sm border border-neutral font-normal text-base-600">
          {activeLabel(activeType)}
        </button>
      }
    >
      {({ close }) => (
        <ul>
          {CONTENT_TYPE_FILTERS.map(({ value, label }) => (
            <li key={label}>
              <button
                className="dropdown-item w-full text-left text-xs"
                onClick={() => {
                  onChange(value)
                  close()
                }}
              >
                {label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Dropdown>
  )
}
