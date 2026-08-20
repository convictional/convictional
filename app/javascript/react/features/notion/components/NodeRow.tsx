import { indentRem } from "~/react/features/notion/constants"
import type { NotionTreeNode } from "~/react/features/notion/types"
import { withReturnTo } from "~/react/shared/returnTo"
import { DateTime } from "~/react/ui/DateTime"

interface NodeRowProps {
  node: NotionTreeNode
  depth: number
  onToggleExpanded: (id: string) => void
  onToggleSelection: (id: string, selected: boolean) => void
}

// Two-state rule for folders ("reflect descendants"): a folder is checked only when
// EVERY page under it is selected, and unchecked otherwise — including partial
// selection and the not-yet-authoritative case (we can't claim "all selected" until
// a subtree resolves).
//
// A page is itself an importable document, so its own selection counts alongside its
// descendants — otherwise a selected page with no (or not-all) selected children would
// wrongly read as unchecked. A database is just a container and isn't selectable itself.
function isFolderChecked(node: NotionTreeNode): boolean {
  if (!node.counts_authoritative) return false
  const ownTotal = node.kind === "page" ? 1 : 0
  const ownSelected = node.kind === "page" && node.is_selected_for_sync ? 1 : 0
  const total = node.total_descendant_count + ownTotal
  const selected = node.selected_descendant_count + ownSelected
  if (total === 0) return false
  return selected >= total
}

export function NodeRow({ node, depth, onToggleExpanded, onToggleSelection }: NodeRowProps) {
  // A node with children is a folder: its checkbox cascades selection to everything beneath it
  // and reads checked only when every descendant is selected. A childless node is a plain
  // selectable leaf that reflects its own selection.
  const isFolder = node.has_children
  // A page is an importable document in its own right (even when it also has children), so it
  // carries the imported / will-import badges regardless of whether it's a folder.
  const isPage = node.kind === "page"
  const documentHref = node.document_id ? withReturnTo(`/documents/${node.document_id}/edit`) : null
  const typeIcon = node.kind === "database" ? "database" : "description"

  return (
    <div className="flex items-center gap-2 px-3 py-2" style={{ paddingLeft: indentRem(depth) }}>
      {/* Disclosure chevron — flip-on-open via rotate-180, matching
          SnoozeSubmenu.tsx:56. Hidden (kept for alignment) when childless. */}
      {node.has_children ? (
        <button
          type="button"
          className="btn btn-ghost btn-xs btn-square shrink-0"
          aria-label={node.expanded ? "Collapse" : "Expand"}
          aria-expanded={node.expanded}
          onClick={() => onToggleExpanded(node.notion_node_id)}
        >
          <span className={`material-symbols-outlined text-base ${node.expanded ? "rotate-180" : ""}`} aria-hidden>
            expand_more
          </span>
        </button>
      ) : (
        <span className="w-6 shrink-0" aria-hidden />
      )}

      <input
        type="checkbox"
        className="checkbox checkbox-sm shrink-0"
        checked={isFolder ? isFolderChecked(node) : node.is_selected_for_sync}
        aria-label={`Select ${node.title}`}
        onChange={e => onToggleSelection(node.notion_node_id, e.target.checked)}
      />

      <span className="material-symbols-outlined text-base opacity-60 shrink-0" aria-hidden>
        {typeIcon}
      </span>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{node.title}</p>
      </div>

      {node.resolving && <span className="text-xs opacity-60 shrink-0">Resolving…</span>}

      {node.last_edited_time && (
        <span className="text-xs opacity-60 shrink-0">
          Edited <DateTime datetime={node.last_edited_time} format="relative" />
        </span>
      )}

      {/* Page badges (carried over from PageRow): imported / will-import. Shown for any page,
          including folder pages, since a page is importable even when it has children. */}
      {isPage &&
        (node.is_imported && documentHref ? (
          <a href={documentHref} className="text-xs link link-primary shrink-0">
            Imported · Open document
          </a>
        ) : (
          node.is_selected_for_sync && <span className="text-xs opacity-60 shrink-0">Will import on next sync.</span>
        ))}

      {node.url && (
        <a href={node.url} target="_blank" rel="noopener noreferrer" className="text-xs link shrink-0">
          Open
        </a>
      )}
    </div>
  )
}
