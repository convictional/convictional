import { Skeleton } from "~/react/ui/Skeleton"
import { StickyHeader } from "~/react/ui/StickyHeader"

// Stands in for MeetingShow on first load. Draws its own placeholder sticky
// header so the chrome doesn't pop in when the real one mounts.
export function MeetingShowSkeleton() {
  return (
    <div aria-hidden="true" data-testid="meeting-show-skeleton">
      <StickyHeader>
        <div className="flex items-center justify-between gap-2 p-2">
          <Skeleton className="h-8 w-28" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-8" />
            <Skeleton className="h-8 w-8" />
          </div>
        </div>
      </StickyHeader>
      <div className="space-y-4 px-4">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-3 w-48" />
        <div className="space-y-2 pt-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}
