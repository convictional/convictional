import type { ReactNode } from "react"

import { Dropdown } from "~/react/ui/Dropdown"
import { StickyHeader } from "~/react/ui/StickyHeader"
import type { GroupFilter } from "../types"

interface ChatsHeaderProps {
  groupFilter: GroupFilter
  onGroupFilterChange: (filter: GroupFilter) => void
  composing: boolean
  onToggleCompose: () => void
  // The search input, rendered inline between the filter and the New chat
  // button so it stays pinned with the rest of the sticky header.
  children: ReactNode
}

export function ChatsHeader({
  groupFilter,
  onGroupFilterChange,
  composing,
  onToggleCompose,
  children,
}: ChatsHeaderProps) {
  return (
    <StickyHeader>
      <div className="flex items-start gap-2 p-2">
        <div className="flex items-center gap-2 shrink-0">
          <Dropdown
            placement="bottom-start"
            className="dropdown-card p-2 z-99"
            trigger={
              <button
                type="button"
                className="btn border border-neutral font-normal text-base-600 flex items-center gap-1"
              >
                {groupFilter === "all" ? "All" : "Groups"}
              </button>
            }
          >
            {({ close }) => (
              <ul>
                <li>
                  <button
                    className="dropdown-item text-xs w-full text-left"
                    onClick={() => {
                      onGroupFilterChange("all")
                      close()
                    }}
                  >
                    All
                  </button>
                </li>
                <li>
                  <button
                    className="dropdown-item text-xs w-full text-left"
                    onClick={() => {
                      onGroupFilterChange("groups")
                      close()
                    }}
                  >
                    Groups
                  </button>
                </li>
              </ul>
            )}
          </Dropdown>
        </div>
        {children}
        <button
          onClick={onToggleCompose}
          className="btn border border-neutral font-normal text-base-600 shrink-0 @mobile:btn-square"
        >
          <span className="material-symbols-outlined text-[16px]">{composing ? "close" : "edit_square"}</span>
          <span className="@mobile:hidden">{composing ? "Cancel" : "New chat"}</span>
        </button>
      </div>
    </StickyHeader>
  )
}
