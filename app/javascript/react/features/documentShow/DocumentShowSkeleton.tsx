import { Skeleton } from "~/react/ui/Skeleton"
import { StickyHeader } from "~/react/ui/StickyHeader"

// Stands in for the read-only document view, both as the route's pendingComponent
// and the in-component first-load branch. Draws its own sticky header so the
// chrome doesn't pop in.
export function DocumentShowSkeleton() {
  return (
    <div className="max-w-3xl w-full mx-auto" aria-hidden="true" data-testid="document-show-skeleton">
      <StickyHeader>
        <div className="flex items-center justify-between gap-2 p-2">
          <Skeleton className="h-9 w-40" />
          <Skeleton className="h-9 w-32" />
        </div>
      </StickyHeader>
      <div className="pl-8 pr-12 space-y-4">
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-4 w-48" />
        <div className="space-y-2 pt-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </div>
    </div>
  )
}
