import { type ReactNode, useEffect, useMemo, useRef } from "react"

import { markdownToPlainText } from "~/react/composites/markdown/toPlainText"
import { ResourceBadge } from "~/react/composites/ResourceBadge"
import { CONTENT_TYPE_ICON_STYLES, DECISION_ACCENT_COLOR } from "~/react/shared/contentTypes"
import { withReturnTo } from "~/react/shared/returnTo"
import {
  decisionCount,
  formatAuthor,
  highlightMatches,
  resultNavigationUrl,
  type SearchResult,
} from "~/react/shared/searchResults"
import { DateTime, formatDateTime } from "~/react/ui/DateTime"
import { pluralize } from "~/shared/strings"

interface SearchResultItemProps {
  result: SearchResult
  query: string
  isSelected?: boolean
}

function MetaBadge({ icon, color, children }: { icon: string; color?: string; children: ReactNode }) {
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border"
      style={{ borderColor: `${color}30`, backgroundColor: `${color}08`, color }}
    >
      <span className="material-symbols-outlined !text-xs">{icon}</span>
      <span>{children}</span>
    </span>
  )
}

function hasMetaBadges(result: SearchResult): boolean {
  const meta = result.metadata
  if (result.content_type === "meeting" && meta.scheduled_at) return true
  if (result.content_type === "post" && meta.reaction_count && meta.reaction_count > 0) return true
  if (result.content_type === "email_thread") {
    if ((meta.message_count && meta.message_count > 1) || meta.has_calendar_invite || result.shared_with_me)
      return true
  }
  return decisionCount(result) > 0
}

export function SearchResultItem({ result, query, isSelected }: SearchResultItemProps) {
  const style = CONTENT_TYPE_ICON_STYLES[result.content_type]
  const ref = useRef<HTMLAnchorElement>(null)
  const meta = result.metadata
  const accentColor = style?.color

  useEffect(() => {
    if (isSelected) ref.current?.scrollIntoView({ block: "nearest" })
  }, [isSelected])

  const snippet = useMemo(() => markdownToPlainText(result.preview_content ?? ""), [result.preview_content])
  const showMeta = hasMetaBadges(result)

  return (
    <a
      ref={ref}
      href={withReturnTo(resultNavigationUrl(result))}
      className={`px-4 py-2.5 grid grid-cols-[auto_1fr] gap-x-2 items-start cursor-pointer transition bg-base-50 hover:bg-base-200 ${
        isSelected ? "bg-base-200" : ""
      }`}
    >
      <ResourceBadge contentType={result.content_type} selected={isSelected} />
      <div className="min-w-0">
        <p className="text-sm line-clamp-1 wrap-anywhere">{highlightMatches(result.title, query)}</p>
        {result.preview_content && (
          <p className="text-xs text-base-500 line-clamp-1 wrap-anywhere">{highlightMatches(snippet, query)}</p>
        )}
        <p className="text-xs text-base-500 wrap-anywhere flex items-center gap-1 flex-wrap">
          {result.author && (
            <>
              <span>{highlightMatches(formatAuthor(result.author), query)}</span>
              <span className="text-base-500/50">&middot;</span>
            </>
          )}
          <span className="inline-flex items-center gap-0.5">
            <span className="material-symbols-outlined !text-xs">bolt</span>
            <DateTime datetime={result.updated_at} format="relative" />
          </span>
        </p>
      </div>
      {showMeta && (
        <div className="col-span-2 flex items-center gap-1.5 text-xs mt-1" style={{ color: accentColor }}>
          {result.content_type === "meeting" && meta.scheduled_at && (
            <MetaBadge icon="calendar_month" color={accentColor}>
              {formatDateTime(meta.scheduled_at, "month_day")}
            </MetaBadge>
          )}
          {result.content_type === "post" && !!meta.reaction_count && (
            <MetaBadge icon="favorite" color={accentColor}>
              {meta.reaction_count}
            </MetaBadge>
          )}
          {result.content_type === "email_thread" && (
            <>
              {!!meta.message_count && meta.message_count > 1 && (
                <MetaBadge icon="mail" color={accentColor}>
                  {meta.message_count} {pluralize(meta.message_count, "message")}
                </MetaBadge>
              )}
              {meta.has_calendar_invite && (
                <MetaBadge icon="calendar_month" color={accentColor}>
                  Invite
                </MetaBadge>
              )}
              {result.shared_with_me && (
                <MetaBadge icon="share" color={accentColor}>
                  Shared
                </MetaBadge>
              )}
            </>
          )}
          {decisionCount(result) > 0 && (
            <MetaBadge icon="alt_route" color={DECISION_ACCENT_COLOR}>
              {decisionCount(result)}
            </MetaBadge>
          )}
        </div>
      )}
    </a>
  )
}
