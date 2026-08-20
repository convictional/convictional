import { Skeleton } from "~/react/ui/Skeleton"
import { StickyHeader } from "~/react/ui/StickyHeader"

// Content-only (rows, no header): drops under the real <Header> in DocumentsIndex's
// first-load branch without doubling it. Rows shaped like DocumentRow's grid.
const ROWS = 8

export function DocumentsListSkeleton() {
  return (
    <div className="documents-page" aria-hidden="true" data-testid="documents-list-skeleton">
      {Array.from({ length: ROWS }).map((_, i) => (
        <div key={i} className="grid grid-cols-[1fr] border-b border-base-300 md:grid-cols-[1fr_180px_180px]">
          <div className="px-4 py-6 md:py-5">
            <Skeleton className="h-4 w-1/2" />
          </div>
          <div className="hidden items-center px-4 py-6 md:flex md:py-5">
            <Skeleton className="h-3.5 w-24" />
          </div>
          <div className="hidden items-center px-4 py-6 md:flex md:py-5">
            <Skeleton className="h-3.5 w-20" />
          </div>
        </div>
      ))}
    </div>
  )
}

// Full-page variant for the route's pendingComponent, where the real <Header>
// isn't mounted yet — so it draws its own header placeholder above the rows.
export function DocumentsIndexSkeleton() {
  return (
    <div aria-hidden="true" data-testid="documents-index-skeleton">
      <StickyHeader>
        <div className="flex items-center justify-between gap-2 p-2">
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-8" />
            <Skeleton className="h-8 w-28" />
          </div>
          <Skeleton className="h-8 w-8" />
        </div>
        <div className="hidden grid-cols-[1fr_180px_180px] border-t border-base-300 px-2 md:grid">
          <div className="px-4 py-2">
            <Skeleton className="h-3 w-12" />
          </div>
          <div className="px-4 py-2">
            <Skeleton className="h-3 w-14" />
          </div>
          <div className="px-4 py-2">
            <Skeleton className="h-3 w-20" />
          </div>
        </div>
      </StickyHeader>
      <div className="w-full px-[9px]">
        <DocumentsListSkeleton />
      </div>
    </div>
  )
}
