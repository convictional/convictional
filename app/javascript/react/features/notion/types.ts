import type { PaginatedResponse } from "~/react/shared/types"

// Mirrors `integrations.notion.api.NotionStatusResponse`.
export interface NotionStatus {
  is_connected: boolean
  workspace_name: string | null
  last_synced_at: string | null
}

// Mirrors `integrations.notion.api.NotionConnectionResponse`.
export interface NotionConnectionResult {
  is_connected: boolean
  workspace_name: string | null
}

// Mirrors `integrations.notion.api.NotionSyncStatusResponse`.
export interface NotionSyncStatus {
  last_synced_at: string | null
}

// Mirrors `integrations.notion.api.NotionPageResponse`.
export interface NotionPage {
  notion_page_id: string
  title: string
  parent_id: string | null
  last_edited_time: string | null
  url: string | null
  is_selected_for_sync: boolean
  is_imported: boolean
  document_id: string | null
}

export type NotionNodeKind = "page" | "database"

// Mirrors `integrations.notion.api.NotionNodeResponse`. One row of the lazy
// tree. Folder rows are `kind === "database"` (and pages with children); leaf
// rows are `kind === "page"`. `is_selected_for_sync`/`document_id`/`is_imported`
// are meaningful for leaf pages only; the count fields are meaningful for
// folders only.
export interface NotionNode {
  notion_node_id: string
  kind: NotionNodeKind
  title: string
  parent_id: string | null
  parent_kind: string | null
  has_children: boolean
  url: string | null
  last_edited_time: string | null
  is_selected_for_sync: boolean
  is_imported: boolean
  document_id: string | null
  selected_descendant_count: number
  total_descendant_count: number
  // False until a subtree has been resolved (cascade) or expanded. Governs whether a
  // folder can read as checked: until this is true, the folder's checkbox reads unchecked
  // (we can't claim "all descendants selected" from non-authoritative counts).
  counts_authoritative: boolean
}

// Mirrors `integrations.notion.api.NotionNodeListResponse`.
export interface NotionNodeListResponse extends PaginatedResponse {
  nodes: NotionNode[]
}

// Mirrors `integrations.notion.api.NotionNodeSelectionAcceptedResponse` — the
// 202 echoed back from a folder cascade PATCH so the UI can seed its flip.
export interface NotionNodeSelectionAccepted {
  notion_node_id: string
  kind: NotionNodeKind
  selected_for_sync: boolean
  selected_descendant_count: number
  total_descendant_count: number
  counts_authoritative: boolean
}

// Mirrors `integrations.notion.api.NotionSelectionStateResponse` — polled to
// reconcile an optimistic folder flip against the cascade job's truth.
export type NotionSelectionState = "pending" | "running" | "done" | "failed" | null

export interface NotionSelectionNodeState {
  notion_node_id: string
  selected_descendant_count: number
  total_descendant_count: number
  counts_authoritative: boolean
}

export interface NotionSelectionStateResponse {
  state: NotionSelectionState
  node: NotionSelectionNodeState | null
}

// The normalized client-side representation held in `useNotionTree`'s
// `nodesById` map. Wraps the server `NotionNode` with per-node tree UI state.
//
// Spanning-tree assumption: a node keeps the FIRST parent it was seen under.
// Notion is a DAG (linked databases, multi-parent pages), but we render a
// spanning tree so counts/roll-up follow a single parent edge. Once a node is
// in the map we never rewrite its `parent_id`/`parent_kind` from a later
// sighting under a different parent.
export interface NotionTreeNode extends NotionNode {
  expanded: boolean
  // Loaded child ids, or null = "unloaded sentinel" (never fetched). Empty
  // array = fetched and confirmed childless.
  children: string[] | null
  loadingChildren: boolean
  childrenError: string | null
  childrenCursor: string | null
  childrenHasMore: boolean
  // True while a folder cascade for this subtree is pending/running and the
  // optimistic flip has not yet been reconciled against the server.
  resolving: boolean
}
