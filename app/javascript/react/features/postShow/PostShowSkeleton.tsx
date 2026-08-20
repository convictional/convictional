import { Skeleton } from "~/react/ui/Skeleton"
import { StickyHeader } from "~/react/ui/StickyHeader"

// Stands in for PostShow on first load. Draws its own placeholder sticky header
// so the chrome doesn't pop in when the real one mounts.
const COMMENTS = 2

export function PostShowSkeleton() {
  return (
    <div aria-hidden="true" data-testid="post-show-skeleton" className="mx-auto w-full max-w-3xl space-y-4 px-2">
      <StickyHeader>
        <div className="flex items-center justify-between gap-2 p-2">
          <Skeleton className="h-9 w-24" />
          <div className="flex items-center gap-1">
            <Skeleton className="h-9 w-9" />
            <Skeleton className="h-9 w-9" />
          </div>
        </div>
      </StickyHeader>

      <div className="space-y-3 rounded-2xl border border-base-300 bg-base-50 p-6 shadow-xs">
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-8 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-32" />
            <Skeleton className="h-2.5 w-20" />
          </div>
        </div>
        <Skeleton className="h-6 w-3/4" />
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      </div>

      <div className="mx-2 space-y-4 sm:mx-8">
        {Array.from({ length: COMMENTS }).map((_, i) => (
          <div key={i} className="space-y-2 px-2 pt-2">
            <div className="flex items-center gap-2">
              <Skeleton className="h-6 w-6 rounded-full" />
              <Skeleton className="h-3 w-24" />
            </div>
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-3.5 w-2/3" />
          </div>
        ))}
      </div>
    </div>
  )
}
