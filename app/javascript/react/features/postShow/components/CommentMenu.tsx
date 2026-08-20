import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { Dropdown } from "~/react/ui/Dropdown"

import { copyCommentLink } from "../copyLink"

interface CommentMenuProps {
  commentId: string
  canModify: boolean
  onEdit: () => void
  onDelete: () => void
}

// Per-comment overflow menu. Copy link is available to everyone; Edit and Delete
// only when the viewer authored the comment (canModify). Delete confirms first.
export function CommentMenu({ commentId, canModify, onEdit, onDelete }: CommentMenuProps) {
  async function handleDelete() {
    if (await confirm({ message: "Are you sure you want to delete this?" })) onDelete()
  }

  return (
    <Dropdown
      placement="bottom-end"
      className="dropdown-card p-1 z-50"
      ariaLabel="Comment actions"
      trigger={
        <button
          type="button"
          className="btn btn-square btn-sm btn-ghost opacity-0 group-hover:opacity-100"
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
                void copyCommentLink(commentId)
                close()
              }}
            >
              Copy link
            </button>
          </li>
          {canModify && (
            <>
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
            </>
          )}
        </ul>
      )}
    </Dropdown>
  )
}
