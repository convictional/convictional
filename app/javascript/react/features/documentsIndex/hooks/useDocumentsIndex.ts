import { useInfiniteQuery } from "@tanstack/react-query"
import { useMemo } from "react"

import { documentsListQueryOptions } from "~/react/shared/stores/documents"
import type { DocumentFilter } from "~/react/shared/types"

// The browse list, served by the infinite Query keyed on `filter`. Filter state
// now lives in the route's search params (the index reads it and writes it via
// router navigation), so this hook just adapts useInfiniteQuery's surface to the
// list/sentinel shape the panel renders.
export function useDocumentsIndex(filter: DocumentFilter) {
  const query = useInfiniteQuery(documentsListQueryOptions(filter))

  const documents = useMemo(() => query.data?.pages.flatMap(page => page.documents) ?? [], [query.data])

  return {
    documents,
    loading: query.isLoading,
    loadingMore: query.isFetchingNextPage,
    error: query.isError,
    hasMore: query.hasNextPage,
    // fetchNextPage is stable and no-ops while a page is in flight, so it is safe
    // to hand straight to LoadMoreSentinel's IntersectionObserver callback.
    loadMore: query.fetchNextPage,
  }
}
