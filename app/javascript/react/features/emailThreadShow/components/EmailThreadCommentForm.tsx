import { forwardRef } from "react"

import { ComposeReplyPreview } from "~/react/composites/chat/ComposeReplyPreview"
import { CommentComposer, type CommentComposerFocusHandle } from "~/react/composites/comment/CommentComposer"
import { useCommentSubmit } from "~/react/features/emailThreadShow/hooks/useCommentSubmit"
import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useMentionableUsers } from "~/react/shared/hooks/useMentionableUsers"
import { useTypingBroadcast } from "~/react/shared/hooks/useTypingBroadcast"
import { useWorkspaceCollaboratorIds } from "~/react/shared/hooks/useWorkspaceCollaboratorIds"
import type { EmailThreadComment, ReplyPreview } from "~/react/shared/types"
import { ChannelStream } from "~/types/channels"

interface EmailThreadCommentFormProps {
  workspaceId: string
  threadId: string
  // Called after a successful submit with the created comment. The parent uses
  // it to append the comment locally and scroll to the bottom of the timeline.
  onSent?: (comment: EmailThreadComment) => void
  // Up-arrow-in-empty-composer opens the user's last comment for editing; the
  // parent owns the edit selection.
  onEditPrevious?: () => boolean
  // The comment being quote-replied to, or null. Owned by the parent alongside
  // the edit selection; drives the compose banner and the sent reply_to_id.
  replyingTo?: ReplyPreview | null
  onClearReply?: () => void
}

// Email thread comment composer for the bottom of the thread show page. Posts JSON
// to `/api/email_threads/{threadId}/comments`; the created comment is returned
// and appended to the local list via `onSent`. Other clients receive it via the
// `email_thread_comments` CREATED broadcast (`workspace_events` COMMENTED events
// are intentionally skipped by EmailThreadShow to avoid double-rendering).
//
// Mentions stay collaborator-split because email threads expose collaborators.
export const EmailThreadCommentForm = forwardRef<CommentComposerFocusHandle, EmailThreadCommentFormProps>(
  function EmailThreadCommentForm({ workspaceId, threadId, onSent, onEditPrevious, replyingTo, onClearReply }, ref) {
    const { user: currentUser } = useCurrentUser()
    const collaboratorIds = useWorkspaceCollaboratorIds(workspaceId)
    const mentionableUsers = useMentionableUsers({ collaboratorIds })
    const { send } = useCommentSubmit({ threadId, onSuccess: onSent })
    const { onType, stopTyping } = useTypingBroadcast({
      stream: ChannelStream.EMAIL_THREAD_COMMENTS,
      params: { email_thread_id: threadId },
    })

    return (
      <CommentComposer
        ref={ref}
        testId="comment-form"
        currentUser={currentUser ? { display_name: currentUser.display_name, picture: currentUser.picture } : null}
        mentionableUsers={mentionableUsers}
        uploadUrl={attachmentUploadUrl(workspaceId)}
        replyPreview={
          replyingTo && onClearReply ? <ComposeReplyPreview replyTo={replyingTo} onClear={onClearReply} /> : undefined
        }
        // Gate reply_to_id on the same condition as the banner so a suppressed
        // banner can never smuggle a reply_to_id onto an otherwise-plain comment.
        onSubmit={(content, claimId, unfurlLinks) =>
          send(content, claimId, unfurlLinks, replyingTo && onClearReply ? replyingTo.id : null)
        }
        onEditPrevious={onEditPrevious}
        onType={onType}
        onStopTyping={stopTyping}
        placeholder="Write an internal chat message"
        errorText="Couldn't send comment. Try again."
      />
    )
  }
)
