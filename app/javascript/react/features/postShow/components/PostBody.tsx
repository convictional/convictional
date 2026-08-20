import { useCallback, useState } from "react"

import { ActionSheet } from "~/react/composites/ActionSheet"
import { DecisionMarker } from "~/react/composites/DecisionMarker"
import { DecisionsSummary } from "~/react/composites/DecisionsSummary"
import { Markdown } from "~/react/composites/markdown/Markdown"
import { ReactionBar } from "~/react/composites/reactions/ReactionBar"
import { stripPreviewedAttachmentLink } from "~/react/composites/stripAttachmentLink"
import { UserAvatar } from "~/react/composites/UserAvatar"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useLongPress } from "~/react/shared/hooks/useLongPress"
import type { Decision, PostComment, Post } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"
import { Dropdown } from "~/react/ui/Dropdown"

import { wasEdited } from "../commentTiming"
import { CommentLinkPreview } from "./CommentLinkPreview"
import { PostEditForm } from "./PostEditForm"
import { ReadAnalytics } from "./ReadAnalytics"

interface PostBodyProps {
  post: Post
  originalComment: PostComment | null
  // The full workspace decision list (for the summary) plus the gid index (for
  // the original comment's inline marker) — same data the comment thread uses.
  decisions: Decision[]
  decisionsByGid: Map<string, Decision>
  toggleDecision: (commentGid: string) => void
  currentUserId: string
  onSave: (post: Post, content: string) => void
  onToggleReaction: (reactionType: string) => void
  onJumpToDecision: (commentGid: string) => void
}

function FloatingBadge({ icon, label }: { icon: string; label: string }) {
  return (
    <div className="inline-flex items-center px-2 py-0.5 gap-1">
      <span className="material-symbols-outlined text-sm text-base-600/70">{icon}</span>
      <span className="text-xs text-base-600/70 font-semibold">{label}</span>
    </div>
  )
}

// The post body card: the original comment rendered as the post (author row,
// floating pinned/announcement badges, title, group tag, markdown, link preview),
// the read-analytics row, decision banner, and the original-comment reactions.
// Flips into PostEditForm when the author opens the overflow → Edit.
export function PostBody({
  post,
  originalComment,
  decisions,
  decisionsByGid,
  toggleDecision,
  currentUserId,
  onSave,
  onToggleReaction,
  onJumpToDecision,
}: PostBodyProps) {
  const [editing, setEditing] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const edited = originalComment ? wasEdited(originalComment.created_at, originalComment.updated_at) : false
  const hasFloatingBadge = post.is_pinned || post.is_announcement
  const originalDecision = originalComment ? decisionsByGid.get(originalComment.global_id) : undefined

  // On mobile the hover overflow (Edit) and reaction tooltip are unreachable, so
  // a long-press on the post body (or a reaction chip) opens the action sheet.
  const isMobile = useIsMobile()
  const { handlers: longPress, isPressing, highlight } = useLongPress(useCallback(() => setSheetOpen(true), []))
  const pressable = isMobile && !editing && !!originalComment
  const chipHandlers = isMobile ? longPress : undefined

  return (
    <div className="bg-base-50 rounded-2xl border border-base-300 shadow-xs relative mb-4">
      {editing ? (
        <>
          <div className="absolute left-3 -top-3 dropdown-card rounded-lg inline-flex items-center px-2 py-1 gap-2 shadow-sm">
            <span className="text-xs text-base-600/70 font-semibold">Edit Post</span>
          </div>
          <PostEditForm
            post={post}
            initialContent={originalComment?.content ?? ""}
            onSave={(updated, content) => {
              onSave(updated, content)
              setEditing(false)
            }}
            onCancel={() => setEditing(false)}
          />
        </>
      ) : (
        <>
          {hasFloatingBadge && (
            <div className="absolute left-3 -top-3 dropdown-card rounded-lg inline-flex items-center divide-x divide-base-400 shadow-sm">
              {post.is_pinned && <FloatingBadge icon="push_pin" label="Pinned" />}
              {post.is_announcement && <FloatingBadge icon="campaign" label="Announcement" />}
            </div>
          )}

          <div className={`group space-y-2 ${hasFloatingBadge ? "pt-6 pb-3" : "py-3"}`}>
            <div className="flex items-center justify-between gap-2 px-3">
              <div className="flex items-center gap-2">
                {originalComment && <UserAvatar user={originalComment.user} size="medium" />}
                <div className="text-sm text-base-500">
                  {originalComment && (
                    <span className="font-semibold text-base-content">{originalComment.user.display_name}</span>
                  )}
                  {originalComment && (
                    <span className="ml-2">
                      <DateTime datetime={originalComment.created_at} format="contextual" />
                      {edited && <span className="ml-1">(edited)</span>}
                    </span>
                  )}
                </div>
              </div>
              {post.permissions.edit && !isMobile && (
                <Dropdown
                  placement="bottom-end"
                  className="dropdown-card p-1 z-50"
                  ariaLabel="Post actions"
                  trigger={
                    <button
                      type="button"
                      className="btn btn-square btn-sm btn-ghost opacity-0 group-hover:opacity-100"
                      aria-label="Post actions"
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
                            setEditing(true)
                            close()
                          }}
                        >
                          Edit
                        </button>
                      </li>
                    </ul>
                  )}
                </Dropdown>
              )}
            </div>

            {/* Content and the reaction chips share one press-feedback layer,
                since a reaction chip is also a long-press target. Only the content
                and the chips carry the long-press handlers. */}
            <div
              className={`space-y-2 rounded-lg transition duration-[320ms] ${
                pressable && (isPressing || highlight) ? "scale-[0.99] bg-base-200" : ""
              }`}
            >
              <div
                className={`px-10 space-y-2 touch-pan-y ${pressable ? "select-none touch-callout-none" : ""}`}
                {...(pressable ? longPress : {})}
              >
                <h1 className="text-xl font-accent truncate" title={post.title}>
                  {post.title}
                </h1>
                {post.group && <div className="text-sm text-primary font-medium">@{post.group.name}</div>}
                {originalComment && (
                  <div data-comment-id={originalComment.id}>
                    <Markdown
                      source={stripPreviewedAttachmentLink(originalComment.content, originalComment.link_preview)}
                    />
                    {originalComment.link_preview && <CommentLinkPreview linkPreview={originalComment.link_preview} />}
                  </div>
                )}
              </div>

              {originalComment && (
                <div className="px-10 flex items-center gap-1 flex-wrap">
                  {/* On mobile the undecided "Decide" affordance and add-reaction
                      menu move into the long-press sheet (mirroring chat). */}
                  {(!isMobile || originalDecision) && (
                    <DecisionMarker
                      decision={originalDecision}
                      onToggle={() => toggleDecision(originalComment.global_id)}
                    />
                  )}
                  <ReactionBar
                    reactions={originalComment.reactions}
                    currentUserId={currentUserId}
                    onToggle={onToggleReaction}
                    chipHandlers={chipHandlers}
                    showMenu={!isMobile}
                  />
                </div>
              )}
            </div>
          </div>

          <ReadAnalytics postId={post.id} enabled={post.permissions.delete} />

          <DecisionsSummary decisions={decisions} onJump={onJumpToDecision} />
        </>
      )}

      {sheetOpen && originalComment && (
        // Editors get Edit here (the desktop overflow Edit is hover-only, so it's
        // the only touch path); a post has no inline delete, so onDelete is omitted
        // and no Delete row renders.
        <ActionSheet
          content={originalComment.content}
          author={originalComment.user}
          createdAt={originalComment.created_at}
          edited={edited}
          reactions={originalComment.reactions}
          isOwn={post.permissions.edit}
          decision={originalDecision}
          resourceLabel="post"
          onClose={() => setSheetOpen(false)}
          onReact={onToggleReaction}
          onEdit={() => setEditing(true)}
          onToggleDecision={() => toggleDecision(originalComment.global_id)}
        />
      )}
    </div>
  )
}
