import { memo, useCallback } from "react"

import { indentRem } from "~/react/features/notion/constants"
import type { NotionTreeNode } from "~/react/features/notion/types"
import { NodeRow } from "./NodeRow"

interface TreeNodeProps {
  nodeId: string
  depth: number
  nodesById: Map<string, NotionTreeNode>
  onToggleExpanded: (id: string) => void
  onToggleSelection: (id: string, selected: boolean) => void
  onLoadMoreChildren: (id: string) => void
  onRetryChildren: (id: string) => void
}

// Recursive, data-stateless tree row. Reads its own node and children straight
// from the normalized `nodesById` map; all mutation goes through the keyed
// handlers passed down (stable identities → React.memo on this component keeps
// untouched subtrees from re-rendering, the EmailMessage.tsx:104-107 pattern).
//
// Per-node "Load more" is a deliberate button, not an intersection sentinel:
// per-node IntersectionObservers in a recursive tree are a known footgun.
function TreeNodeImpl({
  nodeId,
  depth,
  nodesById,
  onToggleExpanded,
  onToggleSelection,
  onLoadMoreChildren,
  onRetryChildren,
}: TreeNodeProps) {
  const node = nodesById.get(nodeId)

  const handleLoadMore = useCallback(() => onLoadMoreChildren(nodeId), [onLoadMoreChildren, nodeId])
  const handleRetry = useCallback(() => onRetryChildren(nodeId), [onRetryChildren, nodeId])

  if (!node) return null

  const childIndent = { paddingLeft: indentRem(depth + 1) }

  return (
    <li role="treeitem" aria-expanded={node.has_children ? node.expanded : undefined}>
      <NodeRow node={node} depth={depth} onToggleExpanded={onToggleExpanded} onToggleSelection={onToggleSelection} />

      {node.expanded && (
        <ul role="group" className="list-none">
          {node.loadingChildren && node.children === null ? (
            <li style={childIndent} className="py-2">
              <span className="loading loading-spinner loading-xs" aria-label="Loading" />
            </li>
          ) : node.childrenError && node.children === null ? (
            <li style={childIndent} className="py-2 flex items-center gap-3">
              <span className="text-sm text-error">{node.childrenError}</span>
              <button type="button" className="btn btn-xs btn-ghost" onClick={handleRetry}>
                Retry
              </button>
            </li>
          ) : node.children && node.children.length === 0 ? (
            <li style={childIndent} className="py-2 text-xs opacity-60">
              No pages inside.
            </li>
          ) : (
            <>
              {node.children?.map(childId => (
                <TreeNode
                  key={childId}
                  nodeId={childId}
                  depth={depth + 1}
                  nodesById={nodesById}
                  onToggleExpanded={onToggleExpanded}
                  onToggleSelection={onToggleSelection}
                  onLoadMoreChildren={onLoadMoreChildren}
                  onRetryChildren={onRetryChildren}
                />
              ))}
              {node.childrenHasMore && (
                <li style={childIndent} className="py-2">
                  <button
                    type="button"
                    className={`btn btn-xs btn-ghost${node.loadingChildren ? " loading loading-xs loading-spinner" : ""}`}
                    disabled={node.loadingChildren}
                    onClick={handleLoadMore}
                  >
                    Load more
                  </button>
                </li>
              )}
              {node.childrenError && node.children && node.children.length > 0 && (
                <li style={childIndent} className="py-2 flex items-center gap-3">
                  <span className="text-sm text-error">{node.childrenError}</span>
                  <button type="button" className="btn btn-xs btn-ghost" onClick={handleRetry}>
                    Retry
                  </button>
                </li>
              )}
            </>
          )}
        </ul>
      )}
    </li>
  )
}

export const TreeNode = memo(TreeNodeImpl)
