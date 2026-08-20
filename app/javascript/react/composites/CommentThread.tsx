import { useCallback, useRef, useState } from "react"

import {
  CommentRichTextField,
  type CommentRichTextFieldHandle,
} from "~/react/composites/editor/components/comments/CommentRichTextField"
import { Markdown } from "~/react/composites/markdown/Markdown"
import type { GoalComment, ReactionUser } from "~/react/shared/hooks/useGoalComments"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import { REACTION_EMOJI, REACTIONS, type ReactionType } from "~/react/shared/reactions"
import { DateTime } from "~/react/ui/DateTime"
import { Dropdown } from "~/react/ui/Dropdown"
import { Tooltip } from "~/react/ui/Tooltip"
import { CommentForm } from "./CommentForm"
import { UserAvatar } from "./UserAvatar"

interface CommentThreadProps {
  thread: GoalComment
  currentUserId: string | null
  mentionableUsers?: MentionUser[]
  onReply: (content: string, parentId: string) => Promise<void>
  onEdit: (commentId: string, content: string) => Promise<void>
  onDelete: (commentId: string) => Promise<void>
  onClose: (commentId: string) => Promise<void>
  onToggleReaction: (commentId: string, reactionType: ReactionType) => Promise<void>
}

export function CommentThread({
  thread,
  currentUserId,
  mentionableUsers = [],
  onReply,
  onEdit,
  onDelete,
  onClose,
  onToggleReaction,
}: CommentThreadProps) {
  const handleReply = useCallback(
    async (content: string) => {
      await onReply(content, thread.id)
    },
    [onReply, thread.id]
  )

  return (
    <div className="dropdown-card !overflow-visible p-2 group/thread w-full">
      <SingleComment
        comment={thread}
        currentUserId={currentUserId}
        mentionableUsers={mentionableUsers}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleReaction={onToggleReaction}
        onResolve={!thread.closed_at ? () => onClose(thread.id) : undefined}
      />
      {thread.replies.length > 0 && (
        <div className="mt-2 space-y-2">
          {thread.replies.map((reply, i) => (
            <div key={reply.id} className={i < thread.replies.length - 1 ? "pb-2" : undefined}>
              <SingleComment
                comment={reply}
                currentUserId={currentUserId}
                mentionableUsers={mentionableUsers}
                onEdit={onEdit}
                onDelete={onDelete}
                onToggleReaction={onToggleReaction}
              />
            </div>
          ))}
        </div>
      )}
      {!thread.closed_at && (
        <div className="mt-2">
          <CommentForm placeholder="Reply..." onSubmit={handleReply} mentionableUsers={mentionableUsers} />
        </div>
      )}
    </div>
  )
}

function SingleComment({
  comment,
  currentUserId,
  mentionableUsers = [],
  onEdit,
  onDelete,
  onToggleReaction,
  onResolve,
}: {
  comment: GoalComment
  currentUserId: string | null
  mentionableUsers?: MentionUser[]
  onEdit: (commentId: string, content: string) => Promise<void>
  onDelete: (commentId: string) => Promise<void>
  onToggleReaction: (commentId: string, reactionType: ReactionType) => Promise<void>
  onResolve?: () => void
}) {
  const [editing, setEditing] = useState(false)
  const isOwner = currentUserId === comment.user.id
  const hasReactions = Object.values(comment.reactions).some(users => users.length > 0)
  const editFieldRef = useRef<CommentRichTextFieldHandle>(null)

  async function handleSaveEdit(markdown: string) {
    const trimmed = markdown.trim()
    if (!trimmed) return
    await onEdit(comment.id, trimmed)
    setEditing(false)
  }

  return (
    <div className="flex-1 min-w-0 group/comment">
      <div className="flex items-center gap-1">
        <div className="shrink-0">
          <UserAvatar user={comment.user} />
        </div>
        <div className="flex flex-col">
          <span className="text-xs font-medium">{comment.user.display_name}</span>
          <DateTime
            datetime={comment.created_at}
            format="relative"
            className="text-[10px] text-base-content/40 leading-tight"
          />
        </div>
        <div className="ml-auto flex items-center gap-1">
          {isOwner && <CommentMenu onEdit={() => setEditing(true)} onDelete={() => onDelete(comment.id)} />}
          {onResolve && (
            <Tooltip content="Resolve thread">
              <button
                type="button"
                onClick={onResolve}
                className="text-base-content/30 hover:text-primary transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-xl">check_circle</span>
              </button>
            </Tooltip>
          )}
        </div>
      </div>
      <div className="text-sm text-base-content/70 mt-0.5">
        {editing ? (
          <div className="space-y-1">
            <div className="textarea textarea-bordered w-full min-h-[2rem] overflow-hidden">
              <CommentRichTextField
                ref={editFieldRef}
                initialContent={comment.content}
                autoFocus
                mentionableUsers={mentionableUsers}
                className="max-h-40 overflow-y-auto focus:outline-hidden"
                onSend={handleSaveEdit}
                onEscape={() => setEditing(false)}
              />
            </div>
            <div className="flex gap-1">
              <button type="button" className="btn btn-xs btn-primary" onClick={() => editFieldRef.current?.submit()}>
                Save
              </button>
              <button type="button" className="btn btn-xs" onClick={() => setEditing(false)}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-1 -mx-1 px-1 rounded group-hover/comment:bg-base-400 transition-colors">
            <div className="flex-1 min-w-0">
              <Markdown source={comment.content} variant="compact" className="mt-0.5" />
            </div>
            {!hasReactions && (
              <ReactionTrigger onToggle={reactionType => onToggleReaction(comment.id, reactionType)} />
            )}
          </div>
        )}
        <ReactionBadges
          reactions={comment.reactions}
          currentUserId={currentUserId}
          onToggle={reactionType => onToggleReaction(comment.id, reactionType)}
        />
      </div>
    </div>
  )
}

function CommentMenu({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) {
  return (
    <Dropdown
      placement="bottom-end"
      className="dropdown-card p-1 z-50 min-w-[120px]"
      trigger={({ ref, ...refProps }) => (
        <Tooltip content="Actions">
          <button
            ref={ref as React.Ref<HTMLButtonElement>}
            type="button"
            className="text-base-content/30 hover:text-primary transition-colors cursor-pointer"
            {...refProps}
          >
            <span className="material-symbols-outlined text-xl">more_horiz</span>
          </button>
        </Tooltip>
      )}
    >
      {({ close }) => (
        <>
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
          <button
            type="button"
            className="dropdown-item w-full text-left text-xs"
            onClick={() => {
              onDelete()
              close()
            }}
          >
            Delete
          </button>
        </>
      )}
    </Dropdown>
  )
}

function ReactionTrigger({ onToggle }: { onToggle: (reactionType: ReactionType) => void }) {
  return (
    <Dropdown
      placement="bottom-end"
      className="dropdown-card p-2 flex z-50"
      trigger={
        <button type="button" className="cursor-pointer">
          <span className="material-symbols-outlined text-base hover:text-base-600">mood</span>
        </button>
      }
    >
      {({ close }) => (
        <>
          {REACTIONS.map(r => (
            <button
              key={r.type}
              type="button"
              className="dropdown-item text-xs aspect-square w-7 flex items-center justify-center"
              onClick={() => {
                onToggle(r.type)
                close()
              }}
            >
              <span role="img" aria-label={r.label}>
                {r.emoji}
              </span>
            </button>
          ))}
        </>
      )}
    </Dropdown>
  )
}

function ReactionBadges({
  reactions,
  currentUserId,
  onToggle,
}: {
  reactions: Record<string, ReactionUser[]>
  currentUserId: string | null
  onToggle: (reactionType: ReactionType) => void
}) {
  const hasReactions = Object.values(reactions).some(users => users.length > 0)
  if (!hasReactions) return null

  return (
    <div className="flex items-center gap-1 mt-1 flex-wrap">
      <ReactionTrigger onToggle={onToggle} />
      {Object.entries(reactions).map(([type, users]) => {
        if (users.length === 0) return null
        const currentUserReacted = users.some(u => u.id === currentUserId)
        return (
          <button
            key={type}
            type="button"
            className={`btn btn-sm rounded-full select-none touch-callout-none ${currentUserReacted ? "btn-primary" : ""}`}
            title={users.map(u => u.display_name).join(", ")}
            onClick={() => onToggle(type as ReactionType)}
          >
            <span className="-mb-0.25">{REACTION_EMOJI[type]}</span>
            <span className={`font-semibold ${currentUserReacted ? "text-primary" : "text-base-600"}`}>
              {users.length}
            </span>
          </button>
        )
      })}
    </div>
  )
}
