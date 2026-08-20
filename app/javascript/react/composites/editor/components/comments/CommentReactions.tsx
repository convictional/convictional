import { DecisionMarker } from "~/react/composites/DecisionMarker"
import { useCommentStore } from "~/react/composites/editor/features/comments/CommentStoreContext"
import type { Comment } from "~/react/composites/editor/features/comments/commentThreads"
import { useCommentThreadsContext } from "~/react/composites/editor/features/comments/CommentThreadsContext"
import { useDecisionsContext } from "~/react/composites/editor/features/comments/DecisionsContext"
import { Reactions } from "~/react/composites/reactions/Reactions"
import type { ReactionType } from "~/react/shared/reactions"

export function CommentReactions({ comment }: { comment: Comment }) {
  const currentUserId = useCommentStore(s => s.currentUserId)
  const { toggleReaction } = useCommentThreadsContext()
  const { decisionsByGid, onToggleDecision } = useDecisionsContext()
  const decision = decisionsByGid.get(comment.global_id)
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {onToggleDecision && (
        // Reactions carries its own mt-1; match it on the marker so the pill
        // sits on the same baseline as the reaction chips on this shared row.
        <DecisionMarker className="mt-1" decision={decision} onToggle={() => onToggleDecision(comment.global_id)} />
      )}
      <Reactions
        reactions={comment.reactions}
        currentUserId={currentUserId}
        onToggle={(type: ReactionType) => toggleReaction(comment.id, type)}
        alwaysShowAddButton
      />
    </div>
  )
}
