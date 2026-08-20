import { Skeleton } from "~/react/ui/Skeleton"
import { StickyHeader } from "~/react/ui/StickyHeader"

// Stands in for the email thread on first load. Draws its own placeholder sticky
// header so the chrome doesn't pop in when the real one mounts.
const MESSAGES = 3

export function EmailThreadSkeleton() {
  return (
    <div aria-hidden="true" data-testid="email-thread-skeleton">
      <StickyHeader>
        <div className="border-b border-neutral p-4">
          <Skeleton className="h-6 w-2/3" />
        </div>
        <div className="flex items-center gap-2 p-2">
          <Skeleton className="h-8 w-20" />
          <div className="ml-auto flex items-center gap-2">
            <Skeleton className="h-8 w-8" />
            <Skeleton className="h-8 w-8" />
            <Skeleton className="h-8 w-8" />
          </div>
        </div>
      </StickyHeader>
      <div className="space-y-3 px-4">
        {Array.from({ length: MESSAGES }).map((_, i) => (
          <div key={i} className="space-y-2 rounded-lg border border-base-300 p-3">
            <div className="flex items-center gap-3">
              <Skeleton className="h-8 w-8 rounded-full" />
              <Skeleton className="h-3.5 w-40" />
            </div>
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
          </div>
        ))}
      </div>
    </div>
  )
}
