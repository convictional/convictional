import { useMemo, useRef, useState } from "react"

import { CollectionListRow } from "~/react/composites/meetings/CollectionListRow"
import { MeetingsListHeader } from "~/react/composites/meetings/MeetingsListHeader"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { EmptyState } from "~/react/ui/EmptyState"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { Tooltip } from "~/react/ui/Tooltip"
import { NewCollectionDialog } from "./components/NewCollectionDialog"
import { useCollectionsIndex } from "./hooks/useCollectionsIndex"

// Pseudo collections sit at the top of the list. Like real collections they
// link to a filtered /meetings view (?filter / ?collection_id) but have no
// database row. Kept client-side because they're presentation-only (the
// CollectionPicker on meeting cards never offers them) and their titles are stable.
const PSEUDO_COLLECTIONS = [
  { key: "most_recent", title: "Most Recent", icon: "calendar_clock", href: "/meetings" },
  { key: "uncategorized", title: "Uncategorized", icon: "help", href: "/meetings?filter=uncategorized" },
]

export function MeetingsCollectionsIndex() {
  const view = useCollectionsIndex()
  const [searchExpanded, setSearchExpanded] = useState(false)
  const [query, setQuery] = useState("")
  const [dialogOpen, setDialogOpen] = useState(false)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return view.collections
    return view.collections.filter(c => c.title.toLowerCase().includes(q))
  }, [view.collections, query])

  const visiblePseudos = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return PSEUDO_COLLECTIONS
    return PSEUDO_COLLECTIONS.filter(p => p.title.toLowerCase().includes(q))
  }, [query])

  const hasRows = visiblePseudos.length > 0 || filtered.length > 0

  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef, [filtered, visiblePseudos])

  return (
    <div ref={rootRef}>
      <MeetingsListHeader current="collections" onMeetingCreated={meeting => boostedNavigate(meeting.source_url)} />
      <div className="px-2">
        <div className="flex items-center justify-between gap-2 mb-3 px-1">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-base-content/60 shrink-0">All Collections</h2>
            {searchExpanded && (
              <label className="input input-sm bg-base-200 flex items-center gap-2 min-w-0 max-w-xs flex-1 rounded-full">
                <span className="material-symbols-outlined text-lg text-base-content/50">search</span>
                <input
                  type="text"
                  placeholder="Filter collections..."
                  autoComplete="off"
                  autoFocus
                  className="grow w-full"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Escape") {
                      setSearchExpanded(false)
                      setQuery("")
                    }
                  }}
                />
              </label>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {!searchExpanded && (
              <Tooltip content="Filter collections">
                <button
                  type="button"
                  onClick={() => setSearchExpanded(true)}
                  aria-label="Filter collections"
                  className="btn btn-ghost btn-circle btn-sm"
                >
                  <span className="material-symbols-outlined text-lg">search</span>
                </button>
              </Tooltip>
            )}
            <button type="button" onClick={() => setDialogOpen(true)} className="btn btn-primary">
              <span className="material-symbols-outlined text-lg">add</span>
              New collection
            </button>
          </div>
        </div>

        {view.error ? (
          <ErrorState message="Failed to load collections. Please try refreshing the page." />
        ) : hasRows ? (
          // Pseudo rows are static, so keep them ahead of the loading gate: with no
          // query they render on first paint while real collections stream in below.
          <div className="rounded-2xl border border-base-300 divide-y divide-base-300 overflow-hidden">
            {visiblePseudos.map(pseudo => (
              <CollectionListRow
                key={pseudo.key}
                href={pseudo.href}
                icon={pseudo.icon}
                title={pseudo.title}
                count={pseudo.key === "uncategorized" ? view.uncategorizedCount : undefined}
              />
            ))}
            {filtered.map(c => (
              <CollectionListRow
                key={c.id}
                href={`/meetings?collection_id=${c.id}`}
                icon={c.auto_assigned ? "auto_awesome" : "folder"}
                title={c.title}
                count={c.meeting_count}
              />
            ))}
          </div>
        ) : view.loading ? (
          <LoadingState />
        ) : (
          // Nothing — real or pseudo — matches the query. With no query the pseudo
          // rows are always visible, so this only shows during an active filter.
          query.trim().length > 0 && <EmptyState text="No collections match your filter" />
        )}
      </div>
      <NewCollectionDialog isOpen={dialogOpen} onClose={() => setDialogOpen(false)} onCreate={view.create} />
    </div>
  )
}
