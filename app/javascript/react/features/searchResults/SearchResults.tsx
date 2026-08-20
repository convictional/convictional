import { useRef } from "react"

import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { EmptyState } from "~/react/ui/EmptyState"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { ContentTypeFilter } from "./components/ContentTypeFilter"
import { HeroResultCard } from "./components/HeroResultCard"
import { SearchResultItem } from "./components/SearchResultItem"
import { useSearchResults } from "./hooks/useSearchResults"

interface SearchResultsProps {
  initialQuery?: string
}

export function SearchResults({ initialQuery }: SearchResultsProps) {
  const {
    results,
    heroCount,
    loading,
    error,
    query,
    contentType,
    selectedIndex,
    setQuery,
    setContentType,
    handleKeyDown,
  } = useSearchResults(initialQuery || "")

  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef, [results, heroCount])

  const hasResults = results.length > 0
  const showInitialSpinner = loading && !hasResults
  const showEmptyPrompt = !loading && !error && query.length < 2 && !hasResults
  const showNoResults = !loading && !error && query.length >= 2 && !hasResults

  return (
    <div ref={rootRef} onKeyDown={handleKeyDown}>
      <StickyHeader>
        <div className="relative flex items-center bg-base-50 rounded-full border border-base-300 shadow-xs">
          <span className="material-symbols-outlined !text-lg absolute left-3.5 text-base-500 pointer-events-none">
            search
          </span>
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search..."
            autoFocus
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            className="w-full pl-10 pr-24 py-3 bg-transparent outline-none text-base"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2 z-10">
            {loading && hasResults && <span className="loading loading-spinner loading-xs" />}
            <ContentTypeFilter activeType={contentType} onChange={setContentType} />
          </div>
        </div>
      </StickyHeader>

      <div className="px-2">
        {showInitialSpinner && <LoadingState />}

        {error && <ErrorState message="Failed to load search results. Please try refreshing the page." />}

        {showEmptyPrompt && <EmptyState text="Enter a search query to find content" />}

        {showNoResults && (
          <EmptyState title={`No results found for "${query}"`} text="Try different keywords or remove filters" />
        )}

        {hasResults && (
          <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
            {heroCount >= 1 && (
              <div className="mb-2">
                <HeroResultCard result={results[0]} query={query} isSelected={selectedIndex === 0} />
              </div>
            )}
            {results.length > (heroCount >= 1 ? 1 : 0) && (
              <div className="divide-y divide-base-300 border border-base-300 rounded-2xl overflow-hidden shadow-xs">
                {results.slice(heroCount >= 1 ? 1 : 0).map((result, i) => {
                  const globalIndex = i + (heroCount >= 1 ? 1 : 0)
                  return (
                    <SearchResultItem
                      key={result.id}
                      result={result}
                      query={query}
                      isSelected={globalIndex === selectedIndex}
                    />
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
