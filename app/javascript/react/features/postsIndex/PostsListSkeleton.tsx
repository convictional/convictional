import { Skeleton } from "~/react/ui/Skeleton"

// Content-only: PostsIndex keeps its header and new-post form mounted above the
// loading branch, so this fills just the post list (no header of its own).
const CARDS = 4

export function PostsListSkeleton() {
  return (
    <ol
      aria-hidden="true"
      data-testid="posts-list-skeleton"
      className="divide-y divide-base-300 overflow-hidden rounded-2xl border border-base-300 shadow-xs"
    >
      {Array.from({ length: CARDS }).map((_, i) => (
        <li key={i} className="space-y-2 bg-base-50 px-6 py-4">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </li>
      ))}
    </ol>
  )
}
