import { Skeleton } from "~/react/ui/Skeleton"
import { StickyHeader } from "~/react/ui/StickyHeader"

// Stands in for GoalShow on first load. Draws its own placeholder sticky header
// so the chrome doesn't pop in when the real one mounts.
export function GoalShowSkeleton() {
  return (
    <div aria-hidden="true" data-testid="goal-show-skeleton">
      <StickyHeader>
        <div className="flex items-center justify-between gap-2 p-2">
          <Skeleton className="h-9 w-28" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-9 w-9" />
            <Skeleton className="h-9 w-9" />
          </div>
        </div>
      </StickyHeader>
      <div className="space-y-4 px-4">
        <Skeleton className="h-8 w-2/3" />
        <div className="flex gap-2">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-5 w-28" />
        </div>
        <div className="space-y-2 pt-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}
