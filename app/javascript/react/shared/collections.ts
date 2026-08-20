import { fetchAllPages } from "~/react/shared/paginate"
import type { MeetingCollectionListItem, MeetingCollectionListResponse } from "~/react/shared/types"

export interface AllCollections {
  collections: MeetingCollectionListItem[]
  // Count of meetings with no collection (the "Uncategorized" pseudo row).
  uncategorizedCount: number
}

// `fetchAllPages` drains the whole cursor-paginated collections list (see its
// doc for why the complete set is needed). `uncategorized_count` is identical
// on every page, so capturing it per page leaves us with the last page's value.
export async function fetchAllCollections(signal?: AbortSignal): Promise<AllCollections> {
  let uncategorizedCount = 0
  const collections = await fetchAllPages(
    "/api/meetings_collections",
    (data: MeetingCollectionListResponse) => data.collections,
    {
      signal,
      onPage: data => {
        uncategorizedCount = data.uncategorized_count
      },
    }
  )
  return { collections, uncategorizedCount }
}
