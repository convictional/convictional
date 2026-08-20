import type { NotionTreeNode } from "~/react/features/notion/types"
import { EmptyState } from "~/react/ui/EmptyState"
import { LoadingState } from "~/react/ui/LoadingState"
import { TreeNode } from "./TreeNode"

interface NotionPageTreeProps {
  topIds: string[]
  nodesById: Map<string, NotionTreeNode>
  loading: boolean
  error: string | null
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
  onToggleExpanded: (id: string) => void
  onToggleSelection: (id: string, selected: boolean) => void
  onLoadMoreChildren: (id: string) => void
  onRetryChildren: (id: string) => void
}

export function NotionPageTree({
  topIds,
  nodesById,
  loading,
  error,
  hasMore,
  loadingMore,
  onLoadMore,
  onToggleExpanded,
  onToggleSelection,
  onLoadMoreChildren,
  onRetryChildren,
}: NotionPageTreeProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col">
        <p className="text-sm font-semibold">Pages</p>
        <p className="text-xs opacity-60">
          Pages and databases your Notion integration can see. Expand a folder to browse inside it. Selecting a folder
          imports every page currently under it — and deselecting it clears them all, including pages you picked
          individually.
        </p>
      </div>
      {loading && topIds.length === 0 ? (
        <LoadingState className="py-8" />
      ) : error ? (
        <div className="text-sm text-error">{error}</div>
      ) : topIds.length === 0 ? (
        <EmptyState
          title="No pages visible"
          text="Share at least one page with your Notion integration, then refresh."
        />
      ) : (
        <>
          <ul role="tree" className="divide-y divide-base-300 border border-neutral rounded-lg bg-base-100 list-none">
            {topIds.map(id => (
              <TreeNode
                key={id}
                nodeId={id}
                depth={0}
                nodesById={nodesById}
                onToggleExpanded={onToggleExpanded}
                onToggleSelection={onToggleSelection}
                onLoadMoreChildren={onLoadMoreChildren}
                onRetryChildren={onRetryChildren}
              />
            ))}
          </ul>
          {hasMore && (
            <div className="flex justify-center">
              <button
                type="button"
                className={`btn btn-sm btn-ghost${loadingMore ? " loading loading-sm loading-spinner" : ""}`}
                disabled={loadingMore}
                onClick={onLoadMore}
              >
                Load more
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
