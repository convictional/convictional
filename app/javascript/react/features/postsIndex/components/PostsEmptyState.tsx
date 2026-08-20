import type { PostsView } from "~/react/features/postsIndex/types"
import { EmptyState } from "~/react/ui/EmptyState"

// Picks the empty-state variant from the active view/filter. The root suppresses
// this entirely when the pinned rail has items.
export function PostsEmptyState({ view, decided }: { view: PostsView; decided: boolean }) {
  if (view === "drafts") {
    return (
      <EmptyState title="No drafts" text="Use 'Save as draft' in the composer above to start a collaborative draft." />
    )
  }
  if (decided) {
    return <EmptyState title="No decisions" text="Posts marked with a decision will appear here." />
  }
  return <EmptyState title="No posts" text="Create your first post above to get started." />
}
