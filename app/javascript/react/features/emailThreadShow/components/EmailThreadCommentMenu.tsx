import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { Dropdown } from "~/react/ui/Dropdown"

interface EmailThreadCommentMenuProps {
  onEdit: () => void
  onDelete: () => Promise<void>
}

// Per-comment overflow menu. Edit swaps the comment into its inline editor;
// Delete confirms before calling onDelete.
export function EmailThreadCommentMenu({ onEdit, onDelete }: EmailThreadCommentMenuProps) {
  async function handleDelete() {
    if (await confirm({ message: "Are you sure you want to delete this comment?" })) await onDelete()
  }

  return (
    <Dropdown
      placement="bottom-end"
      className="dropdown-card p-1 z-50"
      ariaLabel="Comment actions"
      trigger={
        <button
          type="button"
          className="btn btn-square btn-sm btn-ghost opacity-0 transition-opacity group-hover:opacity-100"
          aria-label="Comment actions"
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
              className="dropdown-item text-xs"
              onClick={() => {
                onEdit()
                close()
              }}
            >
              Edit
            </button>
          </li>
          <li>
            <button
              type="button"
              className="dropdown-item text-xs"
              onClick={() => {
                close()
                void handleDelete()
              }}
            >
              Delete
            </button>
          </li>
        </ul>
      )}
    </Dropdown>
  )
}
