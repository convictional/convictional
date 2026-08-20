import { Skeleton } from "~/react/ui/Skeleton"

// Content-only: MeetingsUpcomingIndex keeps its header mounted above the loading
// branch, so this fills just the list. Date-grouped to match the loaded layout.
const GROUPS = 2
const ROWS_PER_GROUP = 3

export function UpcomingListSkeleton() {
  return (
    <div aria-hidden="true" data-testid="upcoming-list-skeleton" className="space-y-4">
      {Array.from({ length: GROUPS }).map((_, g) => (
        <div key={g} className="space-y-2">
          <Skeleton className="h-3 w-24" />
          {Array.from({ length: ROWS_PER_GROUP }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 bg-base-50 px-3 py-3">
              <Skeleton className="h-3 w-12" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-3 w-24" />
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
