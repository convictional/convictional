import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"

import { useClickOutside } from "~/react/shared/hooks/useClickOutside"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useGoalComments } from "~/react/shared/hooks/useGoalComments"
import { useMentionableUsers } from "~/react/shared/hooks/useMentionableUsers"
import { CommentForm } from "./CommentForm"
import { CommentThread } from "./CommentThread"

const PANEL_WIDTH = 320
const VIEWPORT_PADDING = 8

interface CommentsPanelProps {
  goalId: string
  onClose: () => void
}

function usePanelPosition(triggerRef: React.RefObject<HTMLDivElement | null>) {
  const [style, setStyle] = useState<React.CSSProperties>({ opacity: 0 })

  useLayoutEffect(() => {
    function update() {
      const trigger = triggerRef.current
      if (!trigger) return

      const triggerRect = trigger.getBoundingClientRect()
      const gutterRight = triggerRect.right
      const viewportWidth = window.innerWidth

      // Left edge: right side of the gutter column
      let left = gutterRight
      // Clamp so the panel doesn't overflow the viewport
      if (left + PANEL_WIDTH > viewportWidth - VIEWPORT_PADDING) {
        left = viewportWidth - PANEL_WIDTH - VIEWPORT_PADDING
      }

      // Top: align with the trigger, clamp to viewport
      const top = Math.max(VIEWPORT_PADDING, triggerRect.top)

      setStyle(prev => (prev.left === left && prev.top === top ? prev : { left, top, opacity: 1 }))
    }

    update()
    window.addEventListener("scroll", update, true)
    window.addEventListener("resize", update)
    return () => {
      window.removeEventListener("scroll", update, true)
      window.removeEventListener("resize", update)
    }
  }, [triggerRef])

  return style
}

export function CommentsPanel({ goalId, onClose }: CommentsPanelProps) {
  const { user } = useCurrentUser()
  const { comments, loading, createComment, editComment, deleteComment, closeThread, toggleReaction } =
    useGoalComments(goalId)

  // Goal comments are org-wide (no collaborator split), matching the previous
  // /workspaces/collaborators/available behaviour.
  const mentionableUsers = useMentionableUsers()

  const [visible, setVisible] = useState(false)
  const [newThreadOpen, setNewThreadOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLDivElement>(null)

  const positionStyle = usePanelPosition(triggerRef)

  // The comments themselves load through useGoalComments' query on mount; this
  // only runs the fade-in.
  useEffect(() => {
    requestAnimationFrame(() => setVisible(true))
  }, [])

  const closeTimerRef = useRef<ReturnType<typeof setTimeout>>(null)
  useEffect(
    () => () => {
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current)
    },
    []
  )

  const handleClose = useCallback(() => {
    setVisible(false)
    closeTimerRef.current = setTimeout(onClose, 200)
  }, [onClose])

  useClickOutside(panelRef, handleClose)

  const handleNewThread = useCallback(
    async (content: string) => {
      await createComment(content)
      setNewThreadOpen(false)
    },
    [createComment]
  )

  return (
    <>
      <div ref={triggerRef} className="absolute inset-0 pointer-events-none" />
      <div
        ref={panelRef}
        style={{ ...positionStyle, width: PANEL_WIDTH }}
        className={`fixed z-50 p-4 transition-all duration-100 ${
          visible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-2"
        }`}
        // stopPropagation prevents useClickOutside misfires when React re-renders
        // remove a click target (e.g. Reply button replaced by form) before the
        // click event reaches the document listener.
        onClick={e => e.stopPropagation()}
      >
        {loading && comments.length === 0 ? (
          <div className="dropdown-card p-3 w-full flex items-center justify-center py-6">
            <span className="loading loading-spinner loading-sm" />
          </div>
        ) : comments.length === 0 ? (
          <div className="dropdown-card !overflow-visible p-3 w-full">
            <p className="text-xs text-base-content/40 mb-2 text-center">No comments yet</p>
            <CommentForm
              placeholder="Share your thoughts..."
              onSubmit={handleNewThread}
              mentionableUsers={mentionableUsers}
            />
          </div>
        ) : (
          <>
            <div className="space-y-2">
              {comments.map(thread => (
                <CommentThread
                  key={thread.id}
                  thread={thread}
                  currentUserId={user?.id ?? null}
                  mentionableUsers={mentionableUsers}
                  onReply={createComment}
                  onEdit={editComment}
                  onDelete={deleteComment}
                  onClose={closeThread}
                  onToggleReaction={toggleReaction}
                />
              ))}
            </div>
            <div className="dropdown-card !overflow-visible p-2 w-full mt-2">
              {newThreadOpen ? (
                <CommentForm
                  placeholder="Add a comment..."
                  onSubmit={handleNewThread}
                  autoFocus
                  mentionableUsers={mentionableUsers}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setNewThreadOpen(true)}
                  className="w-full text-left text-xs text-base-content/50 hover:text-primary px-1 py-1 transition-colors flex items-center gap-1 rounded cursor-pointer"
                >
                  <span className="material-symbols-outlined text-sm">add</span>
                  <span>Add a comment</span>
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </>
  )
}
