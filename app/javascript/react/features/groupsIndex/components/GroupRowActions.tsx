import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { Dropdown } from "~/react/ui/Dropdown"

interface GroupRowActionsProps {
  groupName: string
  onEdit: () => void
  onDelete: () => void
  triggerClassName?: string
}

export function GroupRowActions({ groupName, onEdit, onDelete, triggerClassName }: GroupRowActionsProps) {
  async function handleDelete(close: () => void) {
    close()
    const confirmed = await confirm({
      message: `Delete ${groupName}? This cannot be undone.`,
      confirmLabel: "Delete",
    })
    if (confirmed) onDelete()
  }

  return (
    <Dropdown
      ariaLabel="Group actions"
      className="dropdown-card menu w-40 p-2 z-50"
      trigger={
        <button
          type="button"
          className={triggerClassName ?? "btn btn-ghost btn-xs btn-circle"}
          aria-label="Group actions"
        >
          <span className="material-symbols-outlined text-base">more_horiz</span>
        </button>
      }
    >
      {({ close }) => (
        <ul>
          <li>
            <button
              type="button"
              className="flex items-center gap-2 w-full text-left"
              onClick={() => {
                close()
                onEdit()
              }}
            >
              <span className="material-symbols-outlined text-lg">edit</span>
              Edit
            </button>
          </li>
          <li>
            <button
              type="button"
              className="flex items-center gap-2 w-full text-left"
              onClick={() => handleDelete(close)}
            >
              <span className="material-symbols-outlined text-lg">delete</span>
              Delete
            </button>
          </li>
        </ul>
      )}
    </Dropdown>
  )
}
