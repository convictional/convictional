import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"

import { markdownToPlainText } from "~/react/composites/markdown/toPlainText"
import { ResourceBadge } from "~/react/composites/ResourceBadge"
import type { FilterMeta, LookupResult, LookupResults } from "~/react/shared/lookup"
import { fetchLookup, fetchPeople, trackSearch } from "~/react/shared/lookup"
import { withReturnTo } from "~/react/shared/returnTo"
import { highlightMatches } from "~/react/shared/searchResults"
import { Avatar } from "~/react/ui/Avatar"
import { DateTime } from "~/react/ui/DateTime"
import { useScrollLock } from "~/react/ui/hooks/useScrollLock"

const DEBOUNCE_MS = 300
const MIN_QUERY_LENGTH = 2
const SEE_ALL_THRESHOLD = 10
const EMPTY_RESULTS: LookupResults = { user_results: [], other_results: [] }

// Morph: "research" (initial, mirrors MobileTopBar) → "search" (active)
type MorphPhase = "research" | "search" | "closing"

interface PendingTracking {
  query: string
  resultIds: string[]
  resultCount: number
  filterGid: string | null
}

export function MobileSearchOverlay() {
  const [isOpen, setIsOpen] = useState(false)
  const [phase, setPhase] = useState<MorphPhase>("research")
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<LookupResults>(EMPTY_RESULTS)
  const [filter, setFilter] = useState<FilterMeta | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const debounceRef = useRef<number | null>(null)
  const requestIdRef = useRef(0)
  const pendingTrackingRef = useRef<PendingTracking | null>(null)

  useEffect(() => {
    const onOpen = () => setIsOpen(true)
    window.addEventListener("mobile-search:open", onOpen)
    return () => window.removeEventListener("mobile-search:open", onOpen)
  }, [])

  useScrollLock(isOpen)

  useEffect(() => {
    if (!isOpen) return
    setPhase("research")

    // Start morph after first paint so "research" state renders first
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setPhase("search")
        setTimeout(() => inputRef.current?.focus(), 0)
      })
    })
  }, [isOpen])

  const flushTracking = useCallback((clickedContentId?: string, clickedPosition?: number) => {
    const pending = pendingTrackingRef.current
    pendingTrackingRef.current = null
    if (!pending || !pending.query) return
    trackSearch({
      query: pending.query,
      result_count: pending.resultCount,
      result_ids: pending.resultIds,
      filter_author_gid: pending.filterGid ?? undefined,
      ...(clickedContentId !== undefined ? { clicked_content_id: clickedContentId } : {}),
      ...(clickedPosition !== undefined ? { clicked_position: clickedPosition } : {}),
    })
  }, [])

  const close = useCallback(() => {
    flushTracking()
    setPhase("closing")
    // Let reverse animation play, then unmount. The flushTracking() above runs
    // synchronously, but the in-flight fetch is aborted on a 300ms delay — so
    // we invalidate requestIdRef and clear pendingTrackingRef inside the timeout
    // to prevent a late-resolving response from polluting the next session's tracking.
    setTimeout(() => {
      setIsOpen(false)
      setPhase("research")
      setQuery("")
      setResults(EMPTY_RESULTS)
      setFilter(null)
      setError(false)
      abortRef.current?.abort()
      requestIdRef.current++
      pendingTrackingRef.current = null
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    }, 300)
  }, [flushTracking])

  // Fetches results based on current filter + query. People endpoint accepts an
  // empty query (returns recent activity by that author); lookup requires
  // MIN_QUERY_LENGTH.
  const fetchResults = useCallback(async (q: string, currentFilter: FilterMeta | null) => {
    abortRef.current?.abort()
    const trimmed = q.trim()
    if (!currentFilter && trimmed.length < MIN_QUERY_LENGTH) {
      setResults(EMPTY_RESULTS)
      setLoading(false)
      setError(false)
      return
    }
    const controller = new AbortController()
    abortRef.current = controller
    const thisRequest = ++requestIdRef.current
    setLoading(true)
    setError(false)
    try {
      const response = currentFilter
        ? await fetchPeople(currentFilter.global_id, trimmed, controller.signal)
        : await fetchLookup(trimmed, controller.signal)
      if (requestIdRef.current !== thisRequest) return
      setResults(response.results)
      const ids = [...response.results.user_results, ...response.results.other_results].map(r => r.id)
      pendingTrackingRef.current = {
        query: trimmed,
        resultIds: ids,
        resultCount: ids.length,
        filterGid: currentFilter?.global_id ?? null,
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return
      if (requestIdRef.current === thisRequest) {
        setError(true)
        setResults(EMPTY_RESULTS)
      }
    } finally {
      if (requestIdRef.current === thisRequest) setLoading(false)
    }
  }, [])

  const scheduleFetch = useCallback(
    (q: string, currentFilter: FilterMeta | null) => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
      debounceRef.current = window.setTimeout(() => {
        debounceRef.current = null
        fetchResults(q, currentFilter)
      }, DEBOUNCE_MS)
    },
    [fetchResults]
  )

  const handleInput = useCallback(
    (value: string) => {
      setQuery(value)
      scheduleFetch(value, filter)
    },
    [scheduleFetch, filter]
  )

  const handlePersonTap = useCallback(
    (result: LookupResult) => {
      const meta: FilterMeta = {
        kind: result.content_type === "user" ? "user" : "contact",
        id: result.id,
        name: result.title,
        email: result.email,
        avatar_url: result.avatar_url,
        global_id: result.global_id,
      }
      setFilter(meta)
      setQuery("")
      setResults(EMPTY_RESULTS)
      // Fetch immediately — no debounce — since the user expects instant feedback.
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
      fetchResults("", meta)
      inputRef.current?.focus()
    },
    [fetchResults]
  )

  const handleClearFilter = useCallback(() => {
    setFilter(null)
    setResults(EMPTY_RESULTS)
    if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    fetchResults(query, null)
  }, [fetchResults, query])

  const handleResultTap = useCallback(
    (result: LookupResult, position: number) => {
      flushTracking(result.id, position)
    },
    [flushTracking]
  )

  const handleSeeAllTap = useCallback(() => {
    flushTracking()
  }, [flushTracking])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") close()
    },
    [close]
  )

  if (!isOpen) return null

  const { user_results: userResults, other_results: otherResults } = results
  const hasResults = userResults.length > 0 || otherResults.length > 0
  const totalResults = userResults.length + otherResults.length
  const showSeeAll = !filter && totalResults >= SEE_ALL_THRESHOLD
  const minQueryReached = query.trim().length >= MIN_QUERY_LENGTH
  const showEmpty = !loading && !error && !filter && !minQueryReached && !hasResults
  const showNoResults = !loading && !error && (filter || minQueryReached) && !hasResults

  // "search" = morphed to search mode, "research"/"closing" = showing research state
  const isSearchMode = phase === "search"

  return createPortal(
    <div className="fixed inset-0 z-50 flex flex-col" onKeyDown={handleKeyDown}>
      {/* Background */}
      <div className="absolute inset-0 bg-base-100" />

      {/* Pill */}
      <div className="relative px-2 pt-2" style={{ marginTop: "var(--safe-area-inset-top)" }}>
        <div className="flex items-center gap-3 pl-4 rounded-full border bg-base-200/80 border-base-300 h-[48px]">
          {/* Left icon — spin + crossfade */}
          <div className="relative shrink-0 w-[18px] h-[18px] flex items-center justify-center">
            <span
              className="material-symbols-outlined text-lg text-base-content/50 absolute"
              style={{
                opacity: isSearchMode ? 0 : 1,
                transform: isSearchMode ? "rotate(180deg) scale(0.5)" : "rotate(0deg) scale(1)",
                transition: "opacity 300ms var(--ease-premium), transform 300ms var(--ease-premium)",
              }}
            >
              auto_awesome
            </span>
            <span
              className="material-symbols-outlined text-lg text-base-content/50 absolute"
              style={{
                opacity: isSearchMode ? 1 : 0,
                transform: isSearchMode ? "rotate(0deg) scale(1)" : "rotate(-180deg) scale(0.5)",
                transition: "opacity 300ms var(--ease-premium), transform 300ms var(--ease-premium)",
              }}
            >
              search
            </span>
          </div>

          {/* Center — typewriter crossfade */}
          <div className="flex-1 relative h-full">
            {/* "Research..." typewriter — visible when not in search mode */}
            <div className="absolute inset-0 flex items-center pointer-events-none">
              <TypewriterText text="Research..." active={!isSearchMode} enterDelay={60} />
            </div>

            {/* "Search..." typewriter placeholder — visible when in search mode and input empty */}
            <div className="absolute inset-0 flex items-center pointer-events-none">
              <TypewriterText
                text={filter ? `Search ${filter.name.split(" ")[0]}…` : "Search..."}
                active={isSearchMode && query.length === 0}
                enterDelay={60}
              />
            </div>

            {/* Actual input — transparent, always interactive when in search mode */}
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={e => handleInput(e.target.value)}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              className="absolute inset-0 py-2.5 bg-transparent outline-none text-sm"
              style={{
                opacity: isSearchMode ? 1 : 0,
                caretColor: isSearchMode ? "auto" : "transparent",
              }}
            />
          </div>

          {/* Right icon — spin + crossfade search → close */}
          <button
            type="button"
            onClick={close}
            aria-label="Close search"
            className="flex items-center justify-center p-1.5 mr-0.5 cursor-pointer"
          >
            <span className="relative w-8 h-8">
              <span
                className="material-symbols-outlined text-lg w-8 h-8 flex items-center justify-center rounded-full bg-base-content/8 text-base-content/50 absolute inset-0"
                style={{
                  opacity: isSearchMode ? 0 : 1,
                  transform: isSearchMode ? "rotate(90deg) scale(0.7)" : "rotate(0deg) scale(1)",
                  transition: "opacity 250ms var(--ease-premium), transform 250ms var(--ease-premium)",
                }}
              >
                search
              </span>
              <span
                className="material-symbols-outlined text-lg w-8 h-8 flex items-center justify-center rounded-full bg-base-content/8 text-base-content/50 absolute inset-0"
                style={{
                  opacity: isSearchMode ? 1 : 0,
                  transform: isSearchMode ? "rotate(0deg) scale(1)" : "rotate(-90deg) scale(0.7)",
                  transition: "opacity 250ms var(--ease-premium), transform 250ms var(--ease-premium)",
                }}
              >
                close
              </span>
            </span>
          </button>
        </div>
      </div>

      {/* Filter chip */}
      {filter && (
        <div className="relative px-4 pt-3">
          <FilterChip filter={filter} onClear={handleClearFilter} />
        </div>
      )}

      {/* Results */}
      <div
        className="relative flex-1 overflow-y-auto px-2 pt-3 transition-opacity duration-300"
        style={{ opacity: isSearchMode ? 1 : 0 }}
      >
        {loading && !hasResults && (
          <div className="flex justify-center py-12">
            <span className="loading loading-spinner loading-md" />
          </div>
        )}

        {error && (
          <div className="px-4 py-12 text-center text-base-content/50">
            <p className="text-sm">Failed to load results. Try again.</p>
          </div>
        )}

        {showEmpty && (
          <div className="px-4 py-12 text-center text-base-content/40">
            <p className="text-sm">Search across all your content</p>
          </div>
        )}

        {showNoResults && (
          <div className="px-4 py-12 text-center text-base-content/40">
            <p className="text-sm">{filter ? `No results from ${filter.name}` : `No results for "${query}"`}</p>
          </div>
        )}

        {hasResults && (
          <div className={`space-y-3 ${loading ? "opacity-60 transition-opacity" : "transition-opacity"}`}>
            {userResults.length > 0 && (
              <ResultSection title="People">
                {userResults.map((result, i) => (
                  <PersonRow
                    key={result.id}
                    result={result}
                    query={query}
                    onTap={() => handlePersonTap(result)}
                    index={i}
                  />
                ))}
              </ResultSection>
            )}
            {otherResults.length > 0 && (
              <ResultSection title={userResults.length > 0 ? "Content" : null}>
                {otherResults.map((result, i) => (
                  <ContentRow
                    key={result.id}
                    result={result}
                    query={query}
                    onTap={() => handleResultTap(result, userResults.length + i)}
                  />
                ))}
              </ResultSection>
            )}
            {showSeeAll && <SeeAllRow query={query} onTap={handleSeeAllTap} />}
          </div>
        )}
      </div>
    </div>,
    document.body
  )
}

function SeeAllRow({ query, onTap }: { query: string; onTap: () => void }) {
  return (
    <a
      href={`/search?q=${encodeURIComponent(query)}`}
      onClick={onTap}
      className="grid grid-cols-[auto_1fr_auto] gap-2 items-center px-4 py-3 rounded-2xl border border-base-300 bg-base-50 shadow-xs cursor-pointer transition active:bg-base-200"
    >
      <span className="material-symbols-outlined text-lg text-base-500">manage_search</span>
      <p className="text-sm">See all results for &ldquo;{query}&rdquo;</p>
      <span className="material-symbols-outlined text-base text-base-500">arrow_forward</span>
    </a>
  )
}

function FilterChip({ filter, onClear }: { filter: FilterMeta; onClear: () => void }) {
  return (
    <div className="inline-flex items-center gap-2 pl-2 pr-1 py-1 rounded-full bg-base-200 border border-base-300">
      <Avatar displayName={filter.name} picture={filter.avatar_url} size="xs" />
      <span className="text-xs">{filter.name}</span>
      <button
        type="button"
        onClick={onClear}
        aria-label="Clear filter"
        className="flex items-center justify-center w-5 h-5 rounded-full bg-base-content/10 cursor-pointer"
      >
        <span className="material-symbols-outlined !text-xs text-base-content/60">close</span>
      </button>
    </div>
  )
}

function ResultSection({ title, children }: { title: string | null; children: React.ReactNode }) {
  return (
    <div>
      {title && <p className="text-xs text-base-500 px-4 pb-1.5">{title}</p>}
      <div className="divide-y divide-base-300 border border-base-300 rounded-2xl overflow-hidden shadow-xs bg-base-50">
        {children}
      </div>
    </div>
  )
}

function PersonRow({
  result,
  query,
  onTap,
  index,
}: {
  result: LookupResult
  query: string
  onTap: () => void
  index: number
}) {
  return (
    <button
      type="button"
      onClick={onTap}
      data-position={index}
      className="w-full px-4 py-2.5 grid grid-cols-[auto_1fr] gap-x-3 items-center text-left cursor-pointer transition active:bg-base-200"
    >
      <Avatar displayName={result.title} picture={result.avatar_url} size="large" />
      <div className="min-w-0">
        <p className="text-sm line-clamp-1 wrap-anywhere">{highlightMatches(result.title, query)}</p>
        {result.email && <p className="text-xs text-base-500 line-clamp-1 wrap-anywhere">{result.email}</p>}
      </div>
    </button>
  )
}

function formatAuthors(authors: string[]): string | null {
  if (authors.length === 0) return null
  if (authors.length <= 2) return authors.join(", ")
  const overflow = authors.length - 2
  return `${authors[0]}, ${authors[1]}, and ${overflow} other${overflow === 1 ? "" : "s"}`
}

function ContentRow({ result, query, onTap }: { result: LookupResult; query: string; onTap: () => void }) {
  const authors = formatAuthors(result.authors)
  const snippet = useMemo(() => markdownToPlainText(result.preview ?? ""), [result.preview])
  return (
    <a
      href={withReturnTo(result.url)}
      onClick={onTap}
      className="px-4 py-2.5 grid grid-cols-[auto_1fr] gap-x-2 items-start cursor-pointer transition active:bg-base-200"
    >
      <ResourceBadge contentType={result.content_type} />
      <div className="min-w-0">
        <p className="text-sm line-clamp-1 wrap-anywhere">{highlightMatches(result.title, query)}</p>
        {result.preview && (
          <p className="text-xs text-base-500 line-clamp-1 wrap-anywhere">{highlightMatches(snippet, query)}</p>
        )}
        <p className="text-xs text-base-500 flex items-center gap-1 flex-wrap">
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
      </div>
    </a>
  )
}

// Typewriter: each character staggers its opacity for a reveal/unreveal effect.
// `enterDelay` offsets the entire enter animation so the previous text can fully
// exit before this one starts appearing — prevents overlapping letters.
function TypewriterText({ text, active, enterDelay = 0 }: { text: string; active: boolean; enterDelay?: number }) {
  return (
    <span className="text-base text-base-content/50 whitespace-nowrap">
      {text.split("").map((char, i) => {
        // Enter: wait for enterDelay, then stagger each char by 25ms
        // Exit: stagger in reverse (last char first), no initial delay
        const charDelay = active ? enterDelay + i * 10 : (text.length - 1 - i) * 6
        return (
          <span
            key={i}
            className="inline-block"
            style={{
              opacity: active ? 1 : 0,
              transform: active ? "translateY(0)" : "translateY(4px)",
              transition: `opacity 60ms var(--ease-premium) ${charDelay}ms, transform 60ms var(--ease-premium) ${charDelay}ms`,
            }}
          >
            {char === " " ? " " : char}
          </span>
        )
      })}
    </span>
  )
}
