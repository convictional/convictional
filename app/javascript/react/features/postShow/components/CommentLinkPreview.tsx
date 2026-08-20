import { LinkPreviewCard } from "~/react/composites/chat/LinkPreviewCard"
import type { LinkPreview, PostCommentLinkPreview } from "~/react/shared/types"

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

// Adapts the lean post-comment preview to the richer LinkPreview shape LinkPreviewCard
// renders, deriving the domain the post API doesn't serialize (resource_kind rides through
// the spread, so an attachment link renders as a file card). No dismiss affordance — post
// comments don't remove an unfurled preview after the fact.
export function CommentLinkPreview({ linkPreview }: { linkPreview: PostCommentLinkPreview }) {
  const normalized: LinkPreview = {
    ...linkPreview,
    type: "link",
    site_name: null,
    domain: domainOf(linkPreview.url),
  }

  return (
    <div className="my-3 max-w-lg">
      <LinkPreviewCard linkPreview={normalized} />
    </div>
  )
}
