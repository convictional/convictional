import { Skeleton } from "~/react/ui/Skeleton"

// The body portion (title + content) of DocumentEditorSkeleton, split from the
// header chrome so it mirrors DocumentShowSkeleton's body.
export function DocumentEditorBodySkeleton() {
  return (
    <div aria-hidden="true" data-testid="document-editor-body-skeleton" className="space-y-4 py-2">
      <Skeleton className="h-9 w-2/3" />
      <div className="space-y-2 pt-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    </div>
  )
}
