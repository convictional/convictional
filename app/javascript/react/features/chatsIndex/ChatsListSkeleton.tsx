import { Skeleton } from "~/react/ui/Skeleton"

// Content-only: ChatsIndex keeps its header and search mounted above the loading
// branch, so this fills just the chat list (no header of its own).
const ROWS = 8

export function ChatsListSkeleton() {
  return (
    <div aria-hidden="true" data-testid="chats-list-skeleton">
      {Array.from({ length: ROWS }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 py-3 pl-2 pr-3">
          <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </div>
      ))}
    </div>
  )
}
