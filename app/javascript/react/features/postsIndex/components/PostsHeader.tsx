import type React from "react"
import { useEffect, useRef } from "react"

import { PostsFilterDropdown } from "~/react/features/postsIndex/components/PostsFilterDropdown"
import type { PostsView } from "~/react/features/postsIndex/types"
import type { Group } from "~/react/shared/types"
import { StickyHeader } from "~/react/ui/StickyHeader"

interface PostsHeaderProps {
  isSearch: boolean
  view: PostsView
  groupId: string | null
  decided: boolean
  draftCount: number
  orgGroups: Group[]
  onSelectGroup: (groupId: string | null) => void
  onToggleDecided: () => void
  onShowDrafts: () => void
  onShowPosts: () => void
  // Search
  query: string
  onChangeQuery: (query: string) => void
  onKeyDown: (e: React.KeyboardEvent) => void
  onOpenSearch: () => void
  onCloseSearch: () => void
  searchLoading: boolean
}

// The sticky header. In the posts view it shows the search button, filter
// dropdown, and Decisions/Drafts toggles (Decisions + dropdown are hidden in the
// drafts view). When search opens it swaps to the search input — a full-surface
// takeover (the body swaps separately in the root).
export function PostsHeader(props: PostsHeaderProps) {
  const {
    isSearch,
    view,
    groupId,
    decided,
    draftCount,
    orgGroups,
    onSelectGroup,
    onToggleDecided,
    onShowDrafts,
    onShowPosts,
    query,
    onChangeQuery,
    onKeyDown,
    onOpenSearch,
    onCloseSearch,
    searchLoading,
  } = props

  const isDrafts = view === "drafts"
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isSearch) inputRef.current?.focus()
  }, [isSearch])

  useEffect(() => {
    function handleEscapeWindow(e: KeyboardEvent) {
      if (e.key === "Escape" && isSearch && query === "") onCloseSearch()
    }
    window.addEventListener("keydown", handleEscapeWindow)
    return () => window.removeEventListener("keydown", handleEscapeWindow)
  }, [isSearch, query, onCloseSearch])

  if (isSearch) {
    return (
      <StickyHeader>
        <div className="relative flex items-center" onKeyDown={onKeyDown}>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => onChangeQuery(e.target.value)}
            placeholder="Search posts..."
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            className="w-full pl-4 pr-24 py-3 bg-transparent outline-none text-base"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2 z-10">
            {searchLoading && <span className="loading loading-spinner loading-xs" />}
            <button
              type="button"
              onClick={onCloseSearch}
              className="btn btn-ghost btn-sm btn-square text-base-content/40 hover:text-base-content/70"
              aria-label="Close search"
            >
              <span className="material-symbols-outlined text-lg">close</span>
            </button>
          </div>
        </div>
      </StickyHeader>
    )
  }

  return (
    <StickyHeader>
      <div className="flex items-center gap-2 p-2 min-h-12">
        <button
          type="button"
          onClick={onOpenSearch}
          className="btn btn-square border border-neutral sticky-header-search"
          aria-label="Search posts"
        >
          <span className="material-symbols-outlined text-base">search</span>
        </button>
        {!isDrafts && (
          <>
            <PostsFilterDropdown
              groupId={groupId}
              draftCount={draftCount}
              orgGroups={orgGroups}
              onSelectGroup={onSelectGroup}
              onShowDrafts={onShowDrafts}
            />
            <button
              type="button"
              onClick={onToggleDecided}
              className={`btn ${decided ? "btn-primary" : "border border-neutral font-normal text-base-600"}`}
            >
              Decisions
            </button>
          </>
        )}
        {(draftCount > 0 || isDrafts) && (
          <button
            type="button"
            onClick={isDrafts ? onShowPosts : onShowDrafts}
            className={`btn ${isDrafts ? "btn-primary" : "border border-neutral font-normal text-base-600"}`}
          >
            Drafts{draftCount ? ` (${draftCount})` : ""}
          </button>
        )}
      </div>
    </StickyHeader>
  )
}
