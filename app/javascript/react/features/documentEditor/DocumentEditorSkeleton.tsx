import { Skeleton } from "~/react/ui/Skeleton"
import { StickyHeader } from "~/react/ui/StickyHeader"

import { DocumentEditorBodySkeleton } from "./DocumentEditorBodySkeleton"

// Stands in for DocumentEditor on first load. Draws its own sticky header so the
// chrome doesn't pop in, and reuses the body skeleton. Editor counterpart to
// DocumentShowSkeleton.
export function DocumentEditorSkeleton() {
  return (
    <div aria-hidden="true" data-testid="document-editor-skeleton" className="mx-auto w-full max-w-3xl">
      <StickyHeader>
        <div className="flex items-center gap-2 p-2">
          <Skeleton className="h-8 w-8" />
          <div className="ml-auto flex items-center gap-2">
            <Skeleton className="h-8 w-8" />
            <Skeleton className="h-8 w-8" />
            <Skeleton className="h-8 w-8" />
          </div>
        </div>
      </StickyHeader>
      <div className="mx-auto w-full max-w-4xl">
        <div className="pl-8 pr-12">
          <DocumentEditorBodySkeleton />
        </div>
      </div>
    </div>
  )
}
