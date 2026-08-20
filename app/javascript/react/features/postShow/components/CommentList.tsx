import type { PostComment } from "~/react/shared/types"
import type { CommentThreadProps } from "../commentThread"
import { Comment } from "./Comment"

interface CommentListProps {
  comments: PostComment[]
  ctx: CommentThreadProps
}

// Ordered top-level comments. The original (post-body) comment is rendered
// separately by PostBody, so it never appears here.
export function CommentList({ comments, ctx }: CommentListProps) {
  return (
    <ol className="space-y-4">
      {comments.map(comment => (
        <li key={comment.id} className="transition group relative">
          <div className="px-2 pt-2">
            <Comment comment={comment} ctx={ctx} />
          </div>
        </li>
      ))}
    </ol>
  )
}
