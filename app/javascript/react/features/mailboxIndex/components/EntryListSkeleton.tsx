import { Skeleton } from "~/react/ui/Skeleton"

// Content-only: the mailbox header stays mounted above EntryList, so this fills
// just the entry list. Rows shaped like EntryRow (unread dot + body).
const ROWS = 10

export function EntryListSkeleton() {
  return (
    <ul aria-hidden="true" data-testid="entry-list-skeleton">
      {Array.from({ length: ROWS }).map((_, i) => (
        <li key={i} className="grid grid-cols-[auto_1fr] items-center gap-2 p-2">
          <Skeleton className="h-2 w-2 rounded-full" />
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <Skeleton className="h-3.5 w-40" />
              <Skeleton className="h-3 w-12" />
            </div>
            <Skeleton className="h-3 w-2/3" />
          </div>
        </li>
      ))}
    </ul>
  )
}
