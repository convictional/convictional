import { type ReactNode } from "react"

import type { PaginatedResponse } from "~/react/shared/types"
import { pluralize } from "~/shared/strings"

export interface SearchResultMetadata {
  scheduled_at?: string
  reaction_count?: number
  message_count?: number
  comment_count?: number
  has_calendar_invite?: boolean
  // Decision result: the gid of the decided comment, used to deep-link the result
  // to its anchor in the parent resource.
  comment_gid?: string
  decided_by_id?: string
  resource_gid?: string
  // Parent-resource facet: how many decisions the resource contains.
  decision_count?: number
}

export interface SearchResult {
  id: string
  title: string
  author: string | null
  content_type: string
  category: string
  source_url: string
  preview_content: string | null
  created_at: string
  updated_at: string
  relevance_score: number | null
  metadata: SearchResultMetadata
  shared_with_me: boolean
}

export interface SearchResponse extends PaginatedResponse {
  results: SearchResult[]
  query: string
  content_type: string | null
  hero_count: number
}

function cleanAuthorName(part: string): string {
  const name = part
    .trim()
    .replace(/\s*<[^>]+>/, "")
    .trim()
  if (name) return name
  const match = part.match(/<([^>]+)>/)
  return match ? match[1] : part.trim()
}

function authorNames(author: string): string[] {
  return author.split(",").map(cleanAuthorName).filter(Boolean)
}

// Where a search result navigates. A decision result lands on its decided comment
// via the `#comment-<id>` hash convention the resource islands already read on mount
// (postShow, documentEditor, emailThreadShow); the comment id is the trailing segment
// of the decision's `comment_gid`. Every other result navigates to its source_url.
export function resultNavigationUrl(result: SearchResult): string {
  const commentGid = result.content_type === "decision" ? result.metadata.comment_gid : undefined
  if (!commentGid) return result.source_url
  const commentId = commentGid.split("/").pop()
  return commentId ? `${result.source_url}#comment-${commentId}` : result.source_url
}

// A parent resource (post/document/chat/email thread) can carry a decision_count
// facet; decision result rows themselves do not. Shown as an alt_route + count badge.
export function decisionCount(result: SearchResult): number {
  if (result.content_type === "decision") return 0
  return result.metadata.decision_count ?? 0
}

export function formatAuthor(author: string): string {
  const names = authorNames(author)
  if (names.length <= 2) return names.join(", ")
  const overflow = names.length - 2
  return `${names[0]}, ${names[1]}, and ${overflow} ${pluralize(overflow, "other")}`
}

export function highlightMatches(text: string, query: string): ReactNode {
  if (!query.trim()) return text

  const terms = query
    .trim()
    .split(/\s+/)
    .filter(t => t.length >= 2)
  if (terms.length === 0) return text

  const pattern = new RegExp(`(${terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi")
  const parts = text.split(pattern)

  // split() with a capturing group places matches at odd indices.
  // Wrap in a <span> so highlighted fragments stay inline inside flex parents.
  return (
    <span>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="text-inherit font-bold bg-transparent">
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </span>
  )
}
