import { useEffect, useRef, useState, type ReactNode } from "react"

import { AvatarGroup } from "~/react/composites/AvatarGroup"

import type { PostComment, User } from "~/react/shared/types"
import type { CommentThreadProps } from "../commentThread"
import { ReplyComposer } from "./ReplyComposer"

interface RepliesSectionProps {
  comment: PostComment
  ctx: CommentThreadProps
  // Comment renders each reply; passed as a prop (rather than imported) so the
  // Comment ↔ RepliesSection relationship stays a one-way dependency.
  renderReply: (reply: PostComment) => ReactNode
}

function uniqueReplyAuthors(replies: PostComment[]): User[] {
  const seen = new Set<string>()
  const authors: User[] = []
  for (const reply of replies) {
    if (!seen.has(reply.user.id)) {
      seen.add(reply.user.id)
      authors.push(reply.user)
    }
  }
  return authors
}

// The replies thread under a top-level comment: collapsed (avatar group + count)
// vs expanded (replies list with the curved connector + an "Add a reply"
// composer). Renders nothing when there are no replies; new replies are added
// from the parent comment's Reply button until the first reply exists.
export function RepliesSection({ comment, ctx, renderReply }: RepliesSectionProps) {
  const [expanded, setExpanded] = useState(true)
  const [addingReply, setAddingReply] = useState(false)
  const connectorRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLOListElement>(null)

  // Span the connector from the parent avatar down to the top of the replies
  // list. The list height changes as replies arrive, so track it.
  useEffect(() => {
    if (!expanded) return
    const connector = connectorRef.current
    const list = listRef.current
    if (!connector || !list) return
    const update = () => {
      connector.style.bottom = `${list.offsetHeight}px`
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(list)
    return () => observer.disconnect()
  }, [expanded])

  if (comment.replies.length === 0) return null

  const count = comment.replies.length
  const replyWord = count === 1 ? "reply" : "replies"
  const authors = uniqueReplyAuthors(comment.replies)

  return (
    <div>
      {expanded && (
        // Geometry is coupled to the parent comment's avatar (w-6) and the ol's ml-10.
        <div
          ref={connectorRef}
          className="replies-connector absolute left-3 top-6 w-7 border-l border-b border-base-300 rounded-bl-xl"
        />
      )}
      {!expanded && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="w-full text-left px-2 py-1.5 ml-7 text-xs text-base-500 hover:text-base-content transition flex items-center gap-2"
        >
          <AvatarGroup users={authors} layout="stack" size="small" max={3} withHoverCard />
          <span>
            Show {count} {replyWord}
          </span>
        </button>
      )}
      {expanded && (
        <ol
          ref={listRef}
          className="ml-10 bg-gradient-to-b from-transparent to-base-200 border-l border-b border-r border-base-300 rounded-b-2xl"
        >
          <li className="pl-4 pr-2 @mobile:pr-0 py-1">
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="text-xs text-base-500 hover:text-base-content transition flex items-center gap-1"
            >
              <span className="material-symbols-outlined text-sm">expand_less</span>
              <span>
                Hide {count} {replyWord}
              </span>
            </button>
          </li>
          {comment.replies.map(reply => (
            <li key={reply.id} className="pl-4 pr-2 @mobile:pr-0 py-1.5 transition group">
              {renderReply(reply)}
            </li>
          ))}
          <li className="pl-4 pr-2 @mobile:pr-0 py-2">
            {addingReply ? (
              <ReplyComposer
                workspaceId={ctx.workspaceId}
                autoFocus
                onSubmit={async (content, attachmentClaimId, unfurlLinks) => {
                  const result = await ctx.createComment(content, {
                    parentId: comment.id,
                    attachmentClaimId,
                    unfurlLinks,
                  })
                  if (result) setAddingReply(false)
                  return result
                }}
              />
            ) : (
              <button
                type="button"
                onClick={() => setAddingReply(true)}
                className="btn btn-sm btn-ghost text-base-500"
              >
                <span className="material-symbols-outlined text-base">add</span>
                Add a reply
              </button>
            )}
          </li>
        </ol>
      )}
    </div>
  )
}
