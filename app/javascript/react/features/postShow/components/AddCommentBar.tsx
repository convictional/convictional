import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"

import { PostCommentComposer } from "./PostCommentComposer"

interface AddCommentBarProps {
  workspaceId: string
  // Creates a top-level comment; resolves to the created comment (truthy) on
  // success. The island scrolls the list to the bottom via onSent.
  onSubmit: (content: string, attachmentClaimId: string, unfurlLinks: boolean) => Promise<unknown>
  onSent: () => void
}

// Fixed-bottom composer for top-level comments. The document-style
// PostCommentComposer owns all of its chrome (rounded bar, author avatar,
// formatting toolbar, submit button) and expands on focus, so this just places
// it and adds the scroll-fade spacer.
export function AddCommentBar({ workspaceId, onSubmit, onSent }: AddCommentBarProps) {
  const isMobile = useIsMobile()

  async function handleSubmit(content: string, attachmentClaimId: string, unfurlLinks: boolean) {
    const result = await onSubmit(content, attachmentClaimId, unfurlLinks)
    if (result) onSent()
    return result
  }

  const composer = <PostCommentComposer uploadUrl={attachmentUploadUrl(workspaceId)} onSubmit={handleSubmit} />

  if (isMobile) {
    return (
      <div className="border-t border-base-300 bg-base-100/90 backdrop-blur-xl px-1.5 pt-2">
        {composer}
        <div className="w-full h-2 bg-base-100/90" />
      </div>
    )
  }

  return (
    <>
      <div className="max-w-composer mx-auto">{composer}</div>
      <div className="w-full h-4 bg-base-100" />
    </>
  )
}
