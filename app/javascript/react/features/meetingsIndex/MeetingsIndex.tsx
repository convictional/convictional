import { useRef } from "react"

import { MeetingCard } from "~/react/composites/meetings/MeetingCard"
import { MeetingsListHeader } from "~/react/composites/meetings/MeetingsListHeader"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { EmptyState } from "~/react/ui/EmptyState"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadMoreSentinel } from "~/react/ui/LoadMoreSentinel"
import { CollectionHeader } from "./components/CollectionHeader"
import { useMeetingsIndex } from "./hooks/useMeetingsIndex"
import { MeetingsListSkeleton } from "./MeetingsListSkeleton"
import type { MeetingsIndexProps } from "./types"

// The two permanent pseudo-collections the list renders when no real collection
// is selected. Their labels are static, so we derive them here rather than
// threading query-derived strings through the island.
const PSEUDO_COLLECTIONS = {
  mostRecent: {
    title: "Most Recent",
    description: "Permanent collection containing all recordings you were an attendee of or granted access to",
  },
  uncategorized: {
    title: "Uncategorized",
    description: "Permanent collection containing all recordings that are not in any other collection",
  },
} as const

export function MeetingsIndex({ collectionId, uncategorized, collectionsIndexUrl }: MeetingsIndexProps) {
  const view = useMeetingsIndex({ collectionId, uncategorized })
  const { user } = useCurrentUser()
  const timezone = user?.time_zone ?? null

  // Boost the in-app anchors (the breadcrumb plus each MeetingCard's
  // source_url, which is an in-app /meetings/{id} path) so navigation stays a
  // same-realm swap instead of a hard reload that strands the realm (#8744).
  // Re-process when the collection header arrives and as meeting rows stream in.
  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef, [view.collection, view.meetings])

  const isCollection = collectionId != null
  const pseudo = uncategorized ? PSEUDO_COLLECTIONS.uncategorized : PSEUDO_COLLECTIONS.mostRecent

  // Collection mode needs the collection metadata (for the editable header), which
  // arrives with the first page — so the loading gate waits on it too. Pseudo
  // mode renders its static header in every state.
  const header = isCollection ? (
    view.collection && (
      <CollectionHeader
        collection={view.collection}
        collectionsIndexUrl={collectionsIndexUrl}
        onUpdate={view.updateCollection}
        onDelete={view.deleteCollection}
      />
    )
  ) : (
    <div className="mb-4 px-1">
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm min-w-0">
        <a
          href={collectionsIndexUrl}
          className="text-base-content/60 hover:text-base-content transition-colors shrink-0"
        >
          All Collections
        </a>
        <span className="text-base-content/30 shrink-0">/</span>
        <span className="font-semibold truncate text-base-content">{pseudo.title}</span>
      </nav>
      <p className="text-sm text-base-content/60 mt-1">{pseudo.description}</p>
    </div>
  )

  const loadingFirstPage = view.loading && view.meetings.length === 0 && (!isCollection || !view.collection)
  const showError = view.error || (isCollection && !view.loading && !view.collection)

  let body
  if (loadingFirstPage && !view.error) {
    body = <MeetingsListSkeleton />
  } else if (showError) {
    body = (
      <ErrorState
        message={
          isCollection
            ? "Failed to load this collection. Please try refreshing the page."
            : "Failed to load meetings. Please try refreshing the page."
        }
      />
    )
  } else if (view.meetings.length === 0) {
    body = <EmptyState text="There are no recordings in this collection, or you don't have access to them." />
  } else {
    body = (
      <>
        <div className="rounded-2xl border border-base-300 divide-y divide-base-300 overflow-hidden">
          {view.meetings.map(m => (
            <MeetingCard key={m.id} meeting={m} onMeetingUpdated={view.upsertMeeting} timezone={timezone} />
          ))}
        </div>
        {view.hasMore ? (
          <LoadMoreSentinel onIntersect={view.loadMore} loading={view.loadingMore} />
        ) : (
          <div className="flex gap-2 justify-center py-4">
            <span className="text-base-content/40 text-sm">No more meetings</span>
          </div>
        )}
      </>
    )
  }

  return (
    <div ref={rootRef}>
      <MeetingsListHeader current="collections" onMeetingCreated={meeting => boostedNavigate(meeting.source_url)} />
      <div className="px-2">
        {header}
        {body}
      </div>
    </div>
  )
}
