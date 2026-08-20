import type { Group } from "~/react/shared/types"
import { Dropdown } from "~/react/ui/Dropdown"

interface PostsFilterDropdownProps {
  groupId: string | null
  draftCount: number
  orgGroups: Group[]
  onSelectGroup: (groupId: string | null) => void
  onShowDrafts: () => void
}

// Group / Drafts / Everyone selector, shown only in the posts view. "Drafts"
// switches to the drafts view (a separate collection); a group narrows the
// published feed.
export function PostsFilterDropdown({
  groupId,
  draftCount,
  orgGroups,
  onSelectGroup,
  onShowDrafts,
}: PostsFilterDropdownProps) {
  const selectedGroup = groupId ? orgGroups.find(g => g.id === groupId) : null
  const label = selectedGroup ? selectedGroup.name : "Everyone"

  return (
    <Dropdown
      placement="bottom-start"
      className="dropdown-card z-50"
      trigger={
        <button type="button" className="btn border border-neutral font-normal text-base-600 flex items-center gap-1">
          {label}
        </button>
      }
    >
      {({ close }) => (
        <>
          <ul className="p-2">
            <li>
              <button
                type="button"
                onClick={() => {
                  onShowDrafts()
                  close()
                }}
                className="dropdown-item text-xs w-full text-left"
              >
                <span>Drafts{draftCount ? ` (${draftCount})` : ""}</span>
              </button>
            </li>
          </ul>
          <div className="border-t border-neutral mx-2" />
          <ul className="p-2">
            <li>
              <button
                type="button"
                onClick={() => {
                  onSelectGroup(null)
                  close()
                }}
                className="dropdown-item text-xs w-full text-left"
              >
                <span>Everyone</span>
              </button>
            </li>
            {orgGroups.map(group => (
              <li key={group.id}>
                <button
                  type="button"
                  onClick={() => {
                    onSelectGroup(group.id)
                    close()
                  }}
                  className="dropdown-item text-xs w-full text-left"
                >
                  <span>{group.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </Dropdown>
  )
}
