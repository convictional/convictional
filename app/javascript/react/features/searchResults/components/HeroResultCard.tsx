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

interface HeroResultCardProps {
  result: SearchResult
  query: string
  isSelected?: boolean
}

function HeroBadge({ icon, color, children }: { icon: string; color?: string; children: ReactNode }) {
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs"
      style={{
        borderColor: `${color ?? "#6b7280"}30`,
        backgroundColor: `${color ?? "#6b7280"}08`,
        color,
      }}
    >
      <span className="material-symbols-outlined !text-xs">{icon}</span>
      <span>{children}</span>
    </span>
  )
}

export function HeroResultCard({ result, query, isSelected }: HeroResultCardProps) {
  const style = CONTENT_TYPE_ICON_STYLES[result.content_type]
  const ref = useRef<HTMLAnchorElement>(null)
  const meta = result.metadata
  const accentColor = style?.color ?? "#6b7280"

  useEffect(() => {
    if (isSelected) ref.current?.scrollIntoView({ block: "nearest" })
  }, [isSelected])

  const snippet = useMemo(() => markdownToPlainText(result.preview_content ?? ""), [result.preview_content])

  return (
    <a
      ref={ref}
      href={withReturnTo(resultNavigationUrl(result))}
      className={`block rounded-2xl border shadow-xs overflow-hidden transition cursor-pointer ${
        isSelected ? "bg-base-200 border-base-400" : "bg-base-50 border-base-300 hover:bg-base-200"
      }`}
    >
      <div className="px-4 py-4 grid grid-cols-[auto_1fr] gap-x-2 items-start">
        <ResourceBadge contentType={result.content_type} />
        <div className="min-w-0">
          <p className="text-base font-medium line-clamp-2 wrap-anywhere">{highlightMatches(result.title, query)}</p>
          {result.preview_content && (
            <p className="text-sm text-base-500 line-clamp-3 wrap-anywhere mt-0.5">
              {highlightMatches(snippet, query)}
            </p>
          )}
          <div className="flex items-center gap-1.5 flex-wrap mt-1.5 text-xs text-base-500">
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
          </div>
          {hasAnyBadges(result) && (
            <div className="flex items-center gap-1.5 mt-2" style={{ color: accentColor }}>
              {result.content_type === "meeting" && meta.scheduled_at && (
                <HeroBadge icon="calendar_month" color={accentColor}>
                  {formatDateTime(meta.scheduled_at, "month_day")}
                </HeroBadge>
              )}
              {result.content_type === "post" && !!meta.reaction_count && (
                <HeroBadge icon="favorite" color={accentColor}>
                  {meta.reaction_count}
                </HeroBadge>
              )}
              {result.content_type === "email_thread" && (
                <>
                  {!!meta.message_count && meta.message_count > 1 && (
                    <HeroBadge icon="mail" color={accentColor}>
                      {meta.message_count} {pluralize(meta.message_count, "message")}
                    </HeroBadge>
                  )}
                  {meta.has_calendar_invite && (
                    <HeroBadge icon="calendar_month" color={accentColor}>
                      Invite
                    </HeroBadge>
                  )}
                  {result.shared_with_me && (
                    <HeroBadge icon="share" color={accentColor}>
                      Shared
                    </HeroBadge>
                  )}
                </>
              )}
              {decisionCount(result) > 0 && (
                <HeroBadge icon="alt_route" color={DECISION_ACCENT_COLOR}>
                  {decisionCount(result)}
                </HeroBadge>
              )}
            </div>
          )}
        </div>
      </div>
    </a>
  )
}

function hasAnyBadges(result: SearchResult): boolean {
  const meta = result.metadata
  if (result.content_type === "meeting" && meta.scheduled_at) return true
  if (result.content_type === "post" && meta.reaction_count && meta.reaction_count > 0) return true
  if (result.content_type === "email_thread") {
    if ((meta.message_count && meta.message_count > 1) || meta.has_calendar_invite || result.shared_with_me)
      return true
  }
  return decisionCount(result) > 0
}
