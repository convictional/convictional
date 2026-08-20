import { useNavigate } from "@tanstack/react-router"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { apiFetch } from "~/react/shared/apiFetch"
import { Dropdown } from "~/react/ui/Dropdown"
import { showFlash } from "~/shared/flash"

interface PostHeaderActionsProps {
  postId: string
}

// Header overflow menu — Delete only, rendered when the viewer can delete the
// post (creator or admin). On success the post is gone, so we client-navigate to
// the posts index (the server also returns a Location header for the same target).
export function PostHeaderActions({ postId }: PostHeaderActionsProps) {
  const navigate = useNavigate()

  async function handleDelete() {
    if (!(await confirm({ message: "Are you sure you want to delete this post?" }))) return
    try {
      await apiFetch(`/api/posts/${postId}`, { method: "DELETE" })
      void navigate({ to: "/posts" })
    } catch {
      showFlash("Couldn't delete the post.")
    }
  }

  return (
    <Dropdown
      placement="bottom-end"
      className="dropdown-card p-2 w-72 z-50"
      ariaLabel="Post options"
      trigger={
        <button type="button" className="btn btn-square" aria-label="Post options">
          <span className="material-symbols-outlined text-base">more_horiz</span>
        </button>
      }
    >
      {({ close }) => (
        <ul className="space-y-1">
          <li>
            <button
              type="button"
              onClick={() => {
                close()
                void handleDelete()
              }}
              className="flex-1 w-full flex items-center gap-4 text-left p-2 hover:bg-base-200 rounded-md"
            >
              <span className="material-symbols-outlined text-xl">delete</span>
              <div className="flex flex-col text-left">
                <span className="text-sm font-semibold">Delete</span>
                <span className="text-pretty text-xs opacity-50">Delete this post permanently</span>
              </div>
            </button>
          </li>
        </ul>
      )}
    </Dropdown>
  )
}
