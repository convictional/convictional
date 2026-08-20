import { CommentEditor } from "~/react/composites/comment/CommentEditor"
import type { EmailThreadComment } from "~/react/shared/types"

interface EmailThreadCommentEditorProps {
  comment: EmailThreadComment
  workspaceId: string
  onSave: (content: string, attachmentClaimId: string) => Promise<void>
  onCancel: () => void
}

// Inline editor for an existing thread comment. Mentions stay collaborator-split
// because email threads expose collaborators.
export function EmailThreadCommentEditor({ comment, workspaceId, onSave, onCancel }: EmailThreadCommentEditorProps) {
  return (
    <CommentEditor
      initialContent={comment.content}
      workspaceId={workspaceId}
      onSave={onSave}
      onCancel={onCancel}
      scopeMentionsToCollaborators
    />
  )
}
