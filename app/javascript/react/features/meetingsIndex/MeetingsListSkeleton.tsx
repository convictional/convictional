import { Skeleton } from "~/react/ui/Skeleton"

// Content-only: MeetingsIndex keeps its header mounted above the loading branch,
// so this fills just the card list (no header of its own).
const CARDS = 6

export function MeetingsListSkeleton() {
  return (
    <ul aria-hidden="true" data-testid="meetings-list-skeleton" className="space-y-2">
      {Array.from({ length: CARDS }).map((_, i) => (
        <li key={i} className="rounded-md border border-neutral bg-base-200 px-3 py-2">
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-3 w-32" />
            </div>
            <Skeleton className="h-6 w-24" />
          </div>
        </li>
      ))}
    </ul>
  )
}
