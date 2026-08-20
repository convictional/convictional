import type { PostListDecision } from "~/react/features/postsIndex/types"
import type { Post } from "~/react/shared/types"
import { PostCard } from "./PostCard"

// The pinned-posts rail: a "Pinned" chip over a card list. Rendered only in the
// posts view on the first page (the data hook fetches it with ?pinned=true).
export function PinnedPosts({
  posts,
  decisionsByPostId,
  returnTo,
}: {
  posts: Post[]
  decisionsByPostId: Map<string, PostListDecision>
  returnTo: string
}) {
  if (posts.length === 0) return null

  return (
    <div className="mb-10 relative mt-10">
      <div className="absolute left-3 -top-3 dropdown-card rounded-lg inline-flex items-center px-2 py-0.5 gap-1 shadow-sm z-10">
        <span className="material-symbols-outlined text-sm text-base-600/70">push_pin</span>
        <span className="text-xs text-base-600/70 font-semibold">Pinned</span>
      </div>
      <ol className="border border-base-300 bg-base-50 shadow-xs rounded-2xl divide-y divide-base-300 overflow-hidden">
        {posts.map(post => (
          <PostCard key={post.id} post={post} decision={decisionsByPostId.get(post.id) ?? null} returnTo={returnTo} />
        ))}
      </ol>
    </div>
  )
}
