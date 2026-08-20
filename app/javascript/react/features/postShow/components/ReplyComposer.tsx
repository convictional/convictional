import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"

import { PostCommentComposer } from "./PostCommentComposer"

interface ReplyComposerProps {
  workspaceId: string
  // Resolves to the created comment (truthy) on success so the composer clears,
  // or null on failure so the draft is preserved.
  onSubmit: (content: string, attachmentClaimId: string, unfurlLinks: boolean) => Promise<unknown>
  autoFocus?: boolean
}

// Inline composer pinned at the bottom of an expanded replies thread. Shares the
// document-style PostCommentComposer with the top-level add-comment bar so
// replies get the same formatting toolbar, attachments, GIF, and link-preview
// affordances instead of a divergent chat-style bar.
export function ReplyComposer({ workspaceId, onSubmit, autoFocus }: ReplyComposerProps) {
  return (
    <PostCommentComposer
      uploadUrl={attachmentUploadUrl(workspaceId)}
      onSubmit={onSubmit}
      autoFocus={autoFocus}
      placeholder="Write a reply…"
    />
  )
}
