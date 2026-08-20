import { Skeleton } from "~/react/ui/Skeleton"

// Content-only: GoalsIndex keeps its header mounted above the loading branch, so
// this fills just the row area (no header of its own).
const ROWS = 6

export function GoalsListSkeleton() {
  return (
    <div aria-hidden="true" data-testid="goals-list-skeleton">
      {Array.from({ length: ROWS }).map((_, i) => (
        <div key={i} className="flex items-center justify-between gap-4 border-b border-base-300 py-5 pl-2 pr-4">
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-4 w-1/2" />
          </div>
          <Skeleton className="hidden h-4 w-24 md:block" />
          <Skeleton className="hidden h-4 w-20 md:block" />
        </div>
      ))}
    </div>
  )
}
