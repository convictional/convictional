import { MailboxStateBadge } from "~/react/composites/MailboxStateBadge"
import { ResourceBadge } from "~/react/composites/ResourceBadge"
import { highlightMatches } from "~/react/shared/searchResults"
import { Avatar } from "~/react/ui/Avatar"
import { DateTime } from "~/react/ui/DateTime"

import { iconForContentType } from "../icons"
import type { LookupResult } from "../types"
import { ResultRow } from "./ResultRow"

interface LookupResultRowProps {
  result: LookupResult
  query: string
  isSelected: boolean
  onHover: () => void
  onActivate: () => void
}

function formatAuthors(authors: string[]): string | null {
  if (authors.length === 0) return null
  if (authors.length <= 2) return authors.join(", ")
  const overflow = authors.length - 2
  return `${authors[0]}, ${authors[1]}, and ${overflow} other${overflow === 1 ? "" : "s"}`
}

export function LookupResultRow({ result, query, isSelected, onHover, onActivate }: LookupResultRowProps) {
  const isUser = result.content_type === "user"
  const isContact = result.content_type === "email_contact"
  const isClickable = isUser || isContact

  const icon = isUser ? (
    <Avatar displayName={result.title} picture={result.avatar_url} size="small" />
  ) : isContact ? (
    <span className="material-symbols-outlined text-xl shrink-0 text-info-content">
      {iconForContentType(result.content_type)}
    </span>
  ) : (
    <ResourceBadge contentType={result.content_type} />
  )

  const authors = formatAuthors(result.authors)
  const rowDetails = isClickable ? (
    <>
      <p className="text-sm wrap-anywhere line-clamp-1">{result.title}</p>
      {result.email && <p className="text-xs text-base-500">{result.email}</p>}
    </>
  ) : (
    <>
      {result.content_type === "email_thread" ? (
        <div className="flex items-center gap-1 min-w-0 wrap-anywhere">
          {result.shared_with_me && <MailboxStateBadge variant="shared" />}
          <p className="text-sm line-clamp-1">{highlightMatches(result.title, query)}</p>
        </div>
      ) : (
        <p className="text-sm wrap-anywhere line-clamp-1">{highlightMatches(result.title, query)}</p>
      )}
      {result.preview && (
        <p className="text-xs text-base-500 line-clamp-1 wrap-anywhere">{highlightMatches(result.preview, query)}</p>
      )}
      <p className="text-xs text-base-500 wrap-anywhere flex items-center gap-1 flex-wrap">
        {authors && (
          <>
            <span>{highlightMatches(authors, query)}</span>
            <span className="text-base-500/50">&middot;</span>
          </>
        )}
        <span className="inline-flex items-center gap-0.5">
          <span className="material-symbols-outlined !text-xs">bolt</span>
          <DateTime datetime={result.display_at} format="relative" />
        </span>
      </p>
    </>
  )

  return (
    <ResultRow
      href={isClickable ? undefined : result.url}
      onClick={onActivate}
      onHover={onHover}
      isSelected={isSelected}
      icon={icon}
      rowDetails={rowDetails}
      testId="palette-result"
    />
  )
}
