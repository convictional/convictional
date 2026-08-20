import { useEffect, useRef } from "react"

import { withReturnTo } from "~/react/shared/returnTo"
import { formatAuthor, highlightMatches, type SearchResult } from "~/react/shared/searchResults"
import { DateTime } from "~/react/ui/DateTime"

interface DocumentSearchResultItemProps {
  result: SearchResult
  query: string
  isSelected?: boolean
}

// Search-result source_urls are server-resolved gid links (/gid/<param>), not
// /documents/{id}, so the document id can't be derived client-side — navigation
// is a full load that the server's gid_redirect resolves to the document.
export function DocumentSearchResultItem({ result, query, isSelected }: DocumentSearchResultItemProps) {
  const ref = useRef<HTMLAnchorElement>(null)

  useEffect(() => {
    if (isSelected) ref.current?.scrollIntoView({ block: "nearest" })
  }, [isSelected])

  return (
    <a
      ref={ref}
      href={withReturnTo(result.source_url)}
      className={`grid grid-cols-[1fr] md:grid-cols-[1fr_180px_180px] border-b border-base-300 transition-colors ${
        isSelected ? "bg-base-200/60" : "hover:bg-base-200/60"
      }`}
    >
      <div className="flex flex-col gap-1.5 px-4 py-4 min-w-0 md:flex-row md:items-center md:gap-2 md:py-3">
        <span className="truncate text-base">{highlightMatches(result.title, query)}</span>
        <div className="flex items-center gap-2 flex-wrap md:hidden text-xs">
          {result.author && (
            <span className="text-base-content/80">{highlightMatches(formatAuthor(result.author), query)}</span>
          )}
          <span className="text-base-content/60">
            <DateTime datetime={result.updated_at} format="relative" />
          </span>
        </div>
      </div>
      <div className="hidden md:flex items-center px-4 py-3 text-sm text-base-600 truncate">
        {result.author ? highlightMatches(formatAuthor(result.author), query) : "—"}
      </div>
      <div className="hidden md:flex items-center px-4 py-3 text-sm text-base-600">
        <DateTime datetime={result.updated_at} format="relative" />
      </div>
    </a>
  )
}
