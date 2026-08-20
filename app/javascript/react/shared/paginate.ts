import { apiFetch } from "~/react/shared/apiFetch"
import type { PaginatedResponse } from "~/react/shared/types"

// Eagerly drains every page of a cursor-paginated `/api/` endpoint before
// returning, accumulating the whole list up front. Callers reach for this when
// they need the COMPLETE set in memory — to filter/sort client-side, or to seed
// a stepper with the full order and totals — where a single first page would
// silently drop items past the page size with no signal any are missing.
//
// This is the opposite of `usePaginatedList`, which loads pages lazily on
// demand (infinite scroll / load-more) and never wants the full set at once.
export async function fetchAllPages<T, R extends PaginatedResponse>(
  basePath: string,
  select: (response: R) => T[],
  options?: { signal?: AbortSignal; onPage?: (response: R) => void }
): Promise<T[]> {
  const items: T[] = []
  const seenCursors = new Set<string>()
  let cursor: string | null = null

  do {
    const separator = basePath.includes("?") ? "&" : "?"
    // Both annotations are load-bearing: `url` reads `cursor`, `cursor` is
    // reassigned from `response.next_cursor`, and `response` comes from
    // `apiFetch(url)` — a cycle tsc can't resolve without them (TS7022).
    const url: string = cursor === null ? basePath : `${basePath}${separator}cursor=${encodeURIComponent(cursor)}`
    const response: R = await apiFetch<R>(url, { signal: options?.signal })

    items.push(...select(response))
    options?.onPage?.(response)

    cursor = response.has_more ? response.next_cursor : null
    // A buggy server that reports has_more while handing back a cursor we've
    // already fetched would loop forever, growing `items` unbounded. Bail out.
    if (cursor !== null) {
      if (seenCursors.has(cursor)) break
      seenCursors.add(cursor)
    }
  } while (cursor !== null)

  return items
}
