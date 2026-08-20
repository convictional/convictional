import { type ComponentType, useCallback, useRef } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { Markdown } from "~/react/composites/markdown/Markdown"
import { markdownToPlainText } from "~/react/composites/markdown/toPlainText"
import { UserAvatar } from "~/react/composites/UserAvatar"

import { copyToClipboard } from "~/react/shared/clipboard"
import { useLongPressSheetShield } from "~/react/shared/hooks/useLongPressSheetShield"
import { REACTION_EMOJI, REACTIONS } from "~/react/shared/reactions"
import type { Decision, ReactionUser, User } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"
import { BottomSheet, type BottomSheetHandle } from "~/react/ui/BottomSheet"

// The mobile long-press action sheet shared by chat messages and comment
// surfaces. Both open it identically (react/decide/copy/edit/delete + reactor
// list); the surface-specific bits are props: an optional Reply row, the
// Markdown image renderers, and whether Delete confirms first. Keeping this one
// component is what prevents the two rows' sheets from drifting apart.
interface ActionSheetProps {
  content: string
  // Null only when a comment's author is unresolved; renders a bare avatar then.
  author: User | null
  createdAt: string
  edited: boolean
  reactions: Record<string, ReactionUser[]>
  isOwn: boolean
  // The decision anchored to this item, if any. Undefined means undecided.
  decision?: Decision
  onClose: () => void
  onReact: (reactionType: string) => void
  // Edit and Delete each render only when their handler is passed (and isOwn).
  // Comments/messages pass both; a post passes onEdit alone (it has no inline
  // delete), so the two capabilities are independent rather than coupled.
  onEdit?: () => void
  onDelete?: () => void
  // Omit → no Reply row. Comments reply to the whole thread, not per-item.
  onReply?: () => void
  // Present only when the host wired decisions. Absent → no decision action.
  onToggleDecision?: () => void
  // When set, Delete confirms with this message before firing onDelete; omit for
  // an immediate delete.
  deleteConfirmation?: string
  // Noun for the copy flash ("message" / "comment"); also names the sheet.
  resourceLabel?: string
  // Markdown image renderers for the preview (chat passes ChatImage/gallery;
  // comments render no images).
  imageComponent?: ComponentType<{ src: string; alt: string }>
  imageGroupComponent?: ComponentType<{ images: { src: string; alt: string }[] }>
}

export function ActionSheet({
  content,
  author,
  createdAt,
  edited,
  reactions,
  isOwn,
  decision,
  onClose,
  onReact,
  onEdit,
  onDelete,
  onReply,
  onToggleDecision,
  deleteConfirmation,
  resourceLabel = "message",
  imageComponent,
  imageGroupComponent,
}: ActionSheetProps) {
  const sheetRef = useRef<BottomSheetHandle>(null)
  const { shield } = useLongPressSheetShield()

  // Run an action, then play the slide-down so the sheet doesn't vanish abruptly.
  // The handle's close animation calls `onClose` (unmount) when it finishes.
  const runAndClose = useCallback((action: () => void) => {
    action()
    sheetRef.current?.close()
  }, [])

  const activeReactions = Object.entries(reactions).filter(([, users]) => users.length > 0)
  const label = `${resourceLabel.charAt(0).toUpperCase()}${resourceLabel.slice(1)}`

  return (
    <>
      <BottomSheet ref={sheetRef} ariaLabel={`${label} actions`} onClose={onClose}>
        <div className="flex-1 min-h-0 overflow-y-auto px-4 pb-[calc(1rem+var(--safe-area-inset-bottom))]">
          <div className="mb-4">
            <div className="text-xs mb-1 text-base-content/60 font-medium">
              {author?.display_name}
              <time className="opacity-70 font-normal ml-1">
                {new Date(createdAt).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
              </time>
              {edited && <span className="opacity-70"> (edited)</span>}
            </div>
            <div className="flex items-start gap-2">
              {author ? (
                <UserAvatar user={author} size="medium" />
              ) : (
                <Avatar displayName="" picture={null} size="medium" />
              )}
              <div className="bg-base-100 text-base-900 rounded-2xl p-2 px-3 max-h-32 overflow-y-auto flex-1 min-w-0 select-none">
                <Markdown
                  source={content}
                  variant="compact"
                  imageComponent={imageComponent}
                  imageGroupComponent={imageGroupComponent}
                />
              </div>
            </div>
          </div>

          {activeReactions.length > 0 && (
            <div className="bg-base-100 rounded-2xl p-3 mb-4 max-h-24 overflow-y-auto space-y-3">
              {activeReactions.map(([type, users]) => (
                <div key={type} className="flex items-start gap-3">
                  <span className="text-xl">{REACTION_EMOJI[type]}</span>
                  <span className="text-sm">{users.map(u => u.display_name).join(", ")}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between gap-1 bg-base-100 rounded-full p-1 mb-4 select-none">
            {REACTIONS.map(r => (
              <button
                key={r.type}
                type="button"
                className="btn btn-ghost btn-circle btn-sm"
                onClick={() => runAndClose(() => onReact(r.type))}
              >
                <span role="img" aria-label={r.label} className="text-xl">
                  {r.emoji}
                </span>
              </button>
            ))}
          </div>

          {/* One joined card: join rounds the first/last rows' own corners to
              --radius-field and collapses the shared borders, so a bumped field
              radius gives a heavily-rounded outer edge without clipping. */}
          <div className="join join-vertical w-full [--radius-field:1rem]">
            {onReply && (
              <button
                type="button"
                className="btn btn-lg join-item w-full justify-start gap-3"
                onClick={() => runAndClose(onReply)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  reply
                </span>
                Reply
              </button>
            )}
            {onToggleDecision && (
              <button
                type="button"
                className={`btn btn-lg join-item w-full justify-start gap-3 ${
                  decision ? "bg-decision text-decision-content border-decision-content/25" : ""
                }`}
                onClick={() => runAndClose(onToggleDecision)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  alt_route
                </span>
                {decision ? "Undo decision" : "Mark as decision"}
              </button>
            )}
            <button
              type="button"
              className="btn btn-lg join-item w-full justify-start gap-3"
              onClick={() =>
                runAndClose(
                  () =>
                    // collapse: false preserves paragraph/list line breaks in the clipboard payload
                    void copyToClipboard(markdownToPlainText(content, { collapse: false }), {
                      successMessage: "Copied to clipboard",
                      errorMessage: `Couldn't copy ${resourceLabel}`,
                    })
                )
              }
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                content_copy
              </span>
              Copy
            </button>
            {isOwn && onEdit && (
              <button
                type="button"
                className="btn btn-lg join-item w-full justify-start gap-3"
                onClick={() => runAndClose(onEdit)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  edit
                </span>
                Edit
              </button>
            )}
            {isOwn && onDelete && (
              <button
                type="button"
                className="btn btn-lg join-item w-full justify-start gap-3 text-error-content"
                onClick={() =>
                  runAndClose(() => {
                    if (!deleteConfirmation) {
                      onDelete()
                      return
                    }
                    void confirm({ message: deleteConfirmation }).then(ok => {
                      if (ok) onDelete()
                    })
                  })
                }
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  delete
                </span>
                Delete
              </button>
            )}
          </div>
        </div>
      </BottomSheet>
      {shield}
    </>
  )
}
