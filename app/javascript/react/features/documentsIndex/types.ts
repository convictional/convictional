// The list/filter shapes now live in shared/types.ts so the documents Query
// module (shared/) can read them without importing from a feature. Re-exported
// here so the existing in-feature import paths keep working.
export type { DocumentFilter, DocumentListItem, DocumentListResponse } from "~/react/shared/types"

export type Mode = "browse" | "search"
