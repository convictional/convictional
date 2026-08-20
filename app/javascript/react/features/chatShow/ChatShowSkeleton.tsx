import { Skeleton } from "~/react/ui/Skeleton"
import { StickyHeader } from "~/react/ui/StickyHeader"

// Stands in for ChatShow on first load. Draws its own placeholder sticky header
// so the chrome doesn't pop in. Messages are left-aligned like MessageBubble: an
// avatar leads each run, grouped follow-ups indent under a spacer.
const MESSAGES = [
  { lead: true, w: "w-2/3" },
  { lead: false, w: "w-1/2" },
  { lead: true, w: "w-3/5" },
  { lead: false, w: "w-2/5" },
  { lead: true, w: "w-1/2" },
]

export function ChatShowSkeleton() {
  return (
    <div aria-hidden="true" data-testid="chat-show-skeleton" className="flex h-full flex-col">
      <StickyHeader>
        <div className="flex items-center gap-3 p-3">
          <Skeleton className="h-8 w-8" />
          <Skeleton className="h-8 w-8 rounded-full" />
          <Skeleton className="h-4 w-40" />
          <div className="ml-auto flex items-center gap-2">
            <Skeleton className="h-8 w-8" />
            <Skeleton className="h-8 w-8" />
          </div>
        </div>
      </StickyHeader>
      <div className="flex-1 space-y-3 p-4">
        {MESSAGES.map((m, i) => (
          <div key={i}>
            {m.lead && <Skeleton className="mb-1 ml-8 h-2.5 w-24" />}
            <div className="flex items-start gap-2">
              {m.lead ? <Skeleton className="h-6 w-6 shrink-0 rounded-full" /> : <div className="h-6 w-6 shrink-0" />}
              <Skeleton className={`h-8 ${m.w} max-w-[calc(100%-40px)] rounded-xl`} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
