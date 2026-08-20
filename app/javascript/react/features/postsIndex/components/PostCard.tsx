import { Link } from "@tanstack/react-router"

import { AvatarGroup } from "~/react/composites/AvatarGroup"
import { markdownToPlainText } from "~/react/composites/markdown/toPlainText"
import type { PostListDecision } from "~/react/features/postsIndex/types"
import type { Post } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"

function domainFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

// Published / pinned post card: title, byline (author, group, last-commented),
// content preview, link preview, decision row, comment count + "{n} new" badge,
// and participant avatars — the avatar/comment rows only when comment_count > 0.
// `decision` (from PostListResponse.decisions) is present iff the post is decided.
// `returnTo` is the index URL stamped onto the show page's back link.
export function PostCard({
  post,
  decision = null,
  returnTo,
}: {
  post: Post
  decision?: PostListDecision | null
  returnTo: string
}) {
  const linkPreview = post.link_preview
  const hasLinkPreview = !!linkPreview && (!!linkPreview.title || !!linkPreview.image_url)
  const decisionText = decision?.comment_preview
    ? markdownToPlainText(decision.comment_preview, { maxLength: 60 })
    : ""

  return (
    <li className="bg-base-50 transition group hover:bg-base-200">
      <Link to="/posts/$postId" params={{ postId: post.id }} search={{ return_to: returnTo }} className="block">
        <div className="px-6 py-4 space-y-1.5">
          <h2 className="font-accent text-xl line-clamp-2">{post.title}</h2>
          <p className="text-xs text-base-500 -mt-1">
            by <span className="text-primary">@{post.creator.display_name}</span>
            {post.group && (
              <>
                {" "}
                for <span className="text-primary font-medium">@{post.group.name}</span>
              </>
            )}
            {post.comment_count > 0 && post.last_commented_at && (
              <>
                {" "}
                &middot; <span className="material-symbols-outlined text-sm align-middle">bolt</span>{" "}
                <DateTime datetime={post.last_commented_at} format="relative" />
              </>
            )}
          </p>
          {post.content_preview && <p className="text-sm text-base-600 line-clamp-2">{post.content_preview}</p>}
          {hasLinkPreview && linkPreview && (
            <div
              className={`flex border border-neutral rounded-lg overflow-hidden bg-base-200 ${
                linkPreview.image_url ? "aspect-[3/1] max-h-[150px]" : "max-w-[450px]"
              }`}
            >
              {linkPreview.image_url && (
                <img
                  src={linkPreview.image_url}
                  alt=""
                  className="aspect-square h-full object-cover flex-shrink-0"
                  loading="lazy"
                  onError={e => {
                    e.currentTarget.style.display = "none"
                  }}
                />
              )}
              <div className={`${linkPreview.image_url ? "aspect-[2/1]" : ""} py-2 px-3 min-w-0 overflow-hidden`}>
                {linkPreview.title && <p className="text-sm font-semibold line-clamp-2">{linkPreview.title}</p>}
                {linkPreview.description && (
                  <p className="text-xs text-base-content/50 line-clamp-1 mt-0.5">{linkPreview.description}</p>
                )}
                <p className="text-xs text-base-content/50 mt-0.5">{domainFromUrl(linkPreview.url)}</p>
              </div>
            </div>
          )}
          {decision && (
            <div className="flex items-center gap-1 text-xs text-success-content">
              <span className="material-symbols-outlined text-sm">check_circle</span>
              {decision.count > 1 ? (
                <span className="font-semibold">{decision.count} Decisions</span>
              ) : (
                <>
                  <span className="font-semibold">Decision</span>
                  {decisionText && <span className="text-base-500 truncate">{decisionText}</span>}
                </>
              )}
            </div>
          )}
          {post.comment_count > 0 && (
            <div className="flex items-center gap-3 pt-1 text-xs text-base-500">
              {post.new_comment_count > 0 ? (
                <span className="inline-flex items-center gap-1.5 bg-primary/10 rounded-lg -ml-1.5 pl-1.5 pr-2.5 py-0.5 font-medium text-primary">
                  <span className="material-symbols-outlined text-base">chat_bubble</span>
                  {post.comment_count} · {post.new_comment_count} new
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined text-base">chat_bubble</span>
                  {post.comment_count}
                </span>
              )}
              <AvatarGroup users={post.participants} layout="stack" size="small" max={3} withHoverCard />
            </div>
          )}
        </div>
      </Link>
    </li>
  )
}
