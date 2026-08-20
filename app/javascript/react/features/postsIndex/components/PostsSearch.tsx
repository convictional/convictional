import { useEffect, useRef } from "react"

import type { useSearchOverlay } from "~/react/features/postsIndex/hooks/useSearchOverlay"
import { withReturnTo } from "~/react/shared/returnTo"
import { highlightMatches, type SearchResult } from "~/react/shared/searchResults"
import { EmptyState } from "~/react/ui/EmptyState"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"

// Lightweight search result row (title + snippet + link), reusing the shared
// search-result shape. Search renders generic rows rather than full post cards:
// the full card data (comment_count, decision, new_comment_count) is per-viewer
// and unindexable.
function PostSearchResultItem({
  result,
  query,
  isSelected,
}: {
  result: SearchResult
  query: string
  isSelected: boolean
}) {
  const ref = useRef<HTMLAnchorElement>(null)

  useEffect(() => {
    if (isSelected) ref.current?.scrollIntoView({ block: "nearest" })
  }, [isSelected])

  return (
    <a
      ref={ref}
      href={withReturnTo(result.source_url)}
      className={`block border-b border-base-300 transition-colors ${
        isSelected ? "bg-base-200" : "hover:bg-base-200"
      }`}
    >
      <div className="px-6 py-4 space-y-1">
        <h2 className="font-accent text-xl line-clamp-2">{highlightMatches(result.title, query)}</h2>
        {result.author && <p className="text-xs text-base-500">by {highlightMatches(result.author, query)}</p>}
        {result.preview_content && (
          <p className="text-sm text-base-600 line-clamp-2">{highlightMatches(result.preview_content, query)}</p>
        )}
      </div>
    </a>
  )
}

// The search overlay body. Renders prompt / spinner / empty / results states.
export function PostsSearch({ search }: { search: ReturnType<typeof useSearchOverlay> }) {
  const { results, loading, error, query, searchActive, selectedIndex } = search
  const hasResults = results.length > 0
  const showInitialSpinner = loading && !hasResults && searchActive
  const showEmptyPrompt = !loading && !error && !searchActive && !hasResults
  const showNoResults = !loading && !error && searchActive && !hasResults

  if (error) {
    return <ErrorState message="Failed to search posts. Please try refreshing the page." />
  }
  if (showInitialSpinner) {
    return <LoadingState />
  }
  if (showEmptyPrompt) {
    return <EmptyState text="Enter a search query to find posts" />
  }
  if (showNoResults) {
    return <EmptyState text={`No posts found for "${query}"`} />
  }

  return (
    <ol
      className={`divide-y divide-base-300 border border-base-300 rounded-2xl overflow-hidden shadow-xs ${
        loading ? "opacity-60 transition-opacity" : "transition-opacity"
      }`}
    >
      {results.map((result, i) => (
        <li key={result.id}>
          <PostSearchResultItem result={result} query={query} isSelected={i === selectedIndex} />
        </li>
      ))}
    </ol>
  )
}
