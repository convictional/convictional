import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { useCommentStore } from "~/react/composites/editor/features/comments/CommentStoreContext"
import type { Comment } from "~/react/composites/editor/features/comments/commentThreads"
import { Dropdown } from "~/react/ui/Dropdown"

interface CommentMenuProps {
  comment: Comment
  isFirst: boolean
  onEdit: () => void
  onDelete: () => void
  onResolve: () => void
}

export function CommentMenu({ comment, isFirst, onEdit, onDelete, onResolve }: CommentMenuProps) {
  const currentUserId = useCommentStore(s => s.currentUserId)
  const isOwner = comment.user.id === currentUserId

  if (!isOwner && !isFirst) return null

  return (
    <div className="relative ml-auto">
      <Dropdown
        placement="bottom-end"
        className="dropdown-card w-36 z-50"
        trigger={
          <button type="button" onClick={e => e.stopPropagation()} className="btn btn-ghost btn-sm btn-square">
            <span className="material-symbols-outlined text-sm">more_horiz</span>
          </button>
        }
      >
        {({ close }) => (
          <ul className="p-1" data-comment-portal>
            {isOwner && (
              <li>
                <button
                  type="button"
                  className="dropdown-item w-full text-left text-xs"
                  onClick={() => {
                    onEdit()
                    close()
                  }}
                >
                  Edit
                </button>
              </li>
            )}
            {isOwner && !isFirst && (
              <li>
                <button
                  type="button"
                  className="dropdown-item w-full text-left text-xs"
                  onClick={async () => {
                    close()
                    if (await confirm({ message: "Delete this comment?" })) {
                      onDelete()
                    }
                  }}
                >
                  Delete
                </button>
              </li>
            )}
            {isFirst && (
              <li>
                <button
                  type="button"
                  className="dropdown-item w-full text-left text-xs"
                  onClick={() => {
                    onResolve()
                    close()
                  }}
                >
                  Resolve
                </button>
              </li>
            )}
          </ul>
        )}
      </Dropdown>
    </div>
  )
}
