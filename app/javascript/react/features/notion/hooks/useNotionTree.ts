import { useCallback, useEffect, useRef, useState } from "react"

import type {
  NotionNode,
  NotionNodeListResponse,
  NotionNodeSelectionAccepted,
  NotionSelectionStateResponse,
  NotionTreeNode,
} from "~/react/features/notion/types"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

// 422/502 detail messages are user-facing copy chosen by the API, so we surface
// them inline; everything else falls back to a generic message.
function nodeErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && (error.status === 422 || error.status === 502)) {
    const detail = error.body?.detail
    if (typeof detail === "string") return detail
  }
  return fallback
}

const TREE_LOAD_FALLBACK = "Couldn't load your Notion pages. Please try again."
const CHILDREN_LOAD_FALLBACK = "Couldn't load these pages. Try again."

// How often we poll GET /selection while a folder cascade resolves.
const CASCADE_POLL_INTERVAL_MS = 1500
// 60 × 1500ms ≈ 90s. A cascade still non-terminal after that is treated as
// stuck (lost worker / unavailable record) so the loop always ends and never
// leaves the Sync button permanently disabled.
const MAX_CASCADE_POLLS = 60

// A node is a folder (cascade selection) when it has children — any database, or a
// page that contains sub-pages. A node with no children is a plain selectable leaf.
// We key on has_children, NOT kind: a page with sub-pages must cascade, importing
// itself and everything beneath it.
function isFolder(node: Pick<NotionTreeNode, "has_children">): boolean {
  return node.has_children
}

// Wrap a fresh server node in client-side tree state. Used for top-tier nodes
// and newly-discovered children.
function makeTreeNode(node: NotionNode): NotionTreeNode {
  return {
    ...node,
    expanded: false,
    children: null,
    loadingChildren: false,
    childrenError: null,
    childrenCursor: null,
    childrenHasMore: false,
    resolving: false,
  }
}

export function useNotionTree(enabled: boolean) {
  // Normalized store: every node we've seen, keyed by id. Cascade updates and
  // child appends are O(1). We replace the Map wholesale on each mutation so
  // React sees a new reference and re-renders.
  const [nodesById, setNodesById] = useState<Map<string, NotionTreeNode>>(new Map())
  const [topIds, setTopIds] = useState<string[]>([])

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  // Count of in-flight folder cascades; the Sync button is disabled while > 0.
  const [pendingCascades, setPendingCascades] = useState(0)

  const topCursorRef = useRef<string | null>(null)
  const loadingMoreRef = useRef(false)
  const hasMoreRef = useRef(false)
  hasMoreRef.current = hasMore
  // Latest node state, readable inside async callbacks without stale closures.
  const nodesRef = useRef(nodesById)
  nodesRef.current = nodesById
  // One shared controller per hook instance: reset() and unmount abort every
  // in-flight cascade at once, so an orphaned poll loop can't keep
  // pendingCascades > 0 (which would permanently disable Sync).
  const cascadeAbortRef = useRef<AbortController | null>(null)
  useEffect(() => () => cascadeAbortRef.current?.abort(), [])

  // Patch a single node in the map (no-op if it's gone, e.g. after disconnect).
  const patchNode = useCallback((id: string, patch: Partial<NotionTreeNode>) => {
    setNodesById(prev => {
      const existing = prev.get(id)
      if (!existing) return prev
      const next = new Map(prev)
      next.set(id, { ...existing, ...patch })
      return next
    })
  }, [])

  // Merge a batch of server nodes into the map. Spanning-tree assumption: a node
  // already present keeps its first-seen parent edge and tree UI state; we only
  // refresh the server-derived fields (title, counts, selection, etc.).
  const mergeNodes = useCallback((nodes: NotionNode[]) => {
    setNodesById(prev => {
      const next = new Map(prev)
      for (const node of nodes) {
        const existing = next.get(node.notion_node_id)
        if (existing) {
          next.set(node.notion_node_id, {
            ...existing,
            // Refresh server fields; preserve first-seen parent edge + UI state.
            kind: node.kind,
            title: node.title,
            has_children: node.has_children,
            url: node.url,
            last_edited_time: node.last_edited_time,
            is_selected_for_sync: node.is_selected_for_sync,
            is_imported: node.is_imported,
            document_id: node.document_id,
            selected_descendant_count: node.selected_descendant_count,
            total_descendant_count: node.total_descendant_count,
            counts_authoritative: node.counts_authoritative,
          })
        } else {
          next.set(node.notion_node_id, makeTreeNode(node))
        }
      }
      return next
    })
  }, [])

  const fetchTop = useCallback(
    async (cursor?: string | null) => {
      const isLoadMore = !!cursor
      if (isLoadMore) {
        loadingMoreRef.current = true
        setLoadingMore(true)
      } else {
        setLoading(true)
      }
      setError(null)

      try {
        const url = cursor
          ? `/api/integrations/notion/nodes?cursor=${encodeURIComponent(cursor)}`
          : "/api/integrations/notion/nodes"
        const data = await apiFetch<NotionNodeListResponse>(url, {}, { expectedStatuses: [422, 502] })

        mergeNodes(data.nodes)
        const ids = data.nodes.map(n => n.notion_node_id)
        setTopIds(prev => {
          if (!isLoadMore) return ids
          const seen = new Set(prev)
          return [...prev, ...ids.filter(id => !seen.has(id))]
        })
        topCursorRef.current = data.next_cursor
        setHasMore(data.has_more)
      } catch (e) {
        setError(nodeErrorMessage(e, TREE_LOAD_FALLBACK))
      } finally {
        setLoading(false)
        setLoadingMore(false)
        loadingMoreRef.current = false
      }
    },
    [mergeNodes]
  )

  // Initial top-tier load (and reload when re-enabled, e.g. after connect).
  useEffect(() => {
    if (!enabled) return
    topCursorRef.current = null
    void fetchTop()
  }, [enabled, fetchTop])

  const loadMoreTop = useCallback(() => {
    if (loadingMoreRef.current || !hasMoreRef.current) return
    void fetchTop(topCursorRef.current)
  }, [fetchTop])

  // Fetch one level of a node's children and store them. `append` drains the
  // next page when paginating; otherwise it's the first load.
  const fetchChildren = useCallback(
    async (id: string, cursor: string | null, append: boolean) => {
      patchNode(id, { loadingChildren: true, childrenError: null })
      try {
        // Send the node's kind so the server walks it correctly even before it's persisted: a
        // top-tier database isn't saved until it's expanded or selected, so the DB can't tell the
        // server how to fetch its children (database rows vs. page block children).
        const params = new URLSearchParams()
        if (cursor) params.set("cursor", cursor)
        const kind = nodesRef.current.get(id)?.kind
        if (kind) params.set("kind", kind)
        const query = params.toString()
        const url = query
          ? `/api/integrations/notion/nodes/${encodeURIComponent(id)}/children?${query}`
          : `/api/integrations/notion/nodes/${encodeURIComponent(id)}/children`
        const data = await apiFetch<NotionNodeListResponse>(url, {}, { expectedStatuses: [422, 502] })

        mergeNodes(data.nodes)
        const childIds = data.nodes.map(n => n.notion_node_id)
        setNodesById(prev => {
          const existing = prev.get(id)
          if (!existing) return prev
          const merged = append && existing.children ? existing.children : []
          const seen = new Set(merged)
          const next = new Map(prev)
          next.set(id, {
            ...existing,
            children: [...merged, ...childIds.filter(c => !seen.has(c))],
            childrenCursor: data.next_cursor,
            childrenHasMore: data.has_more,
            loadingChildren: false,
            childrenError: null,
          })
          return next
        })
      } catch (e) {
        patchNode(id, {
          loadingChildren: false,
          childrenError: nodeErrorMessage(e, CHILDREN_LOAD_FALLBACK),
        })
      }
    },
    [mergeNodes, patchNode]
  )

  // Expand a node: reveal it, and lazily fetch children on first expand only.
  // Never refetches a node whose children are already loaded (the
  // EmailMessage.tsx loadContent guard) — collapse/re-expand reuses the cache.
  const expandNode = useCallback(
    (id: string) => {
      const node = nodesRef.current.get(id)
      if (!node) return
      patchNode(id, { expanded: true })
      if (node.children === null && !node.loadingChildren) {
        void fetchChildren(id, null, false)
      }
    },
    [fetchChildren, patchNode]
  )

  const collapseNode = useCallback(
    (id: string) => {
      patchNode(id, { expanded: false })
    },
    [patchNode]
  )

  const toggleExpanded = useCallback(
    (id: string) => {
      const node = nodesRef.current.get(id)
      if (!node) return
      if (node.expanded) collapseNode(id)
      else expandNode(id)
    },
    [collapseNode, expandNode]
  )

  const loadMoreChildren = useCallback(
    (id: string) => {
      const node = nodesRef.current.get(id)
      if (!node || node.loadingChildren || !node.childrenHasMore) return
      void fetchChildren(id, node.childrenCursor, true)
    },
    [fetchChildren]
  )

  const retryChildren = useCallback(
    (id: string) => {
      const node = nodesRef.current.get(id)
      if (!node || node.loadingChildren) return
      void fetchChildren(id, null, false)
    },
    [fetchChildren]
  )

  // Leaf toggle: existing optimistic flip + rollback against PATCH /pages/{id}.
  const toggleLeaf = useCallback(
    (id: string, selected: boolean) => {
      const node = nodesRef.current.get(id)
      if (!node) return
      const previous = node.is_selected_for_sync

      patchNode(id, { is_selected_for_sync: selected })

      apiFetch<NotionNode>(`/api/integrations/notion/pages/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify({
          selected_for_sync: selected,
          title: node.title,
          parent_id: node.parent_id ?? undefined,
          last_edited_time: node.last_edited_time ?? undefined,
        }),
      })
        .then(updated => patchNode(id, { is_selected_for_sync: updated.is_selected_for_sync }))
        .catch(() => patchNode(id, { is_selected_for_sync: previous }))
    },
    [patchNode]
  )

  // Optimistically set a folder + its currently-loaded descendants. The invisible
  // majority is the cascade job's responsibility. Returns a rollback closure
  // capturing the prior selection of every node it touched.
  const optimisticSetSubtree = useCallback((rootId: string, selected: boolean): (() => void) => {
    const touched: Array<{
      id: string
      previousSelected: boolean
      previousCount: number
      previousAuthoritative: boolean
    }> = []
    setNodesById(prev => {
      const next = new Map(prev)
      const stack = [rootId]
      const seen = new Set<string>()
      while (stack.length) {
        const id = stack.pop()
        if (!id || seen.has(id)) continue
        seen.add(id)
        const node = next.get(id)
        if (!node) continue
        touched.push({
          id,
          previousSelected: node.is_selected_for_sync,
          previousCount: node.selected_descendant_count,
          previousAuthoritative: node.counts_authoritative,
        })
        const updated = { ...node, resolving: true }
        // A page is itself an importable document, so its own selection flips.
        if (node.kind === "page") updated.is_selected_for_sync = selected
        // A folder's checkbox reads descendant counts, so flip them to a definite state. We also
        // claim authority: the cascade resolves the whole subtree, so a folder beneath the root is
        // now fully on/off — without this it reads unchecked (counts_authoritative is otherwise
        // false until a node's own cascade), leaving a freshly clicked folder stuck instead of
        // reading checked (on select) or unchecked (on deselect).
        if (node.has_children) {
          updated.selected_descendant_count = selected ? node.total_descendant_count : 0
          updated.counts_authoritative = true
        }
        next.set(id, updated)
        if (node.children) stack.push(...node.children)
      }
      return next
    })

    return () => {
      setNodesById(prev => {
        const next = new Map(prev)
        for (const { id, previousSelected, previousCount, previousAuthoritative } of touched) {
          const node = next.get(id)
          if (node) {
            next.set(id, {
              ...node,
              is_selected_for_sync: previousSelected,
              selected_descendant_count: previousCount,
              counts_authoritative: previousAuthoritative,
            })
          }
        }
        return next
      })
    }
  }, [])

  // Clear the `resolving` flag across a subtree once a cascade terminates.
  const clearResolving = useCallback((rootId: string) => {
    setNodesById(prev => {
      const next = new Map(prev)
      const stack = [rootId]
      const seen = new Set<string>()
      while (stack.length) {
        const id = stack.pop()
        if (!id || seen.has(id)) continue
        seen.add(id)
        const node = next.get(id)
        if (!node) continue
        if (node.resolving) next.set(id, { ...node, resolving: false })
        if (node.children) stack.push(...node.children)
      }
      return next
    })
  }, [])

  // Folder cascade: optimistic flip → PATCH /nodes/{id}/selection (202) → poll
  // GET /selection until done/failed. Server is the source of truth: on done we
  // overwrite local counts + counts_authoritative; on failed we roll back. We do
  // NOT walk ancestors locally — they re-derive from the counts the poll
  // refreshes (and on the next expansion, which re-fetches from the server).
  const toggleFolder = useCallback(
    async (id: string, selected: boolean) => {
      const rollback = optimisticSetSubtree(id, selected)
      setPendingCascades(c => c + 1)

      if (!cascadeAbortRef.current) cascadeAbortRef.current = new AbortController()
      const signal = cascadeAbortRef.current.signal

      // The server needs the node's kind to walk it (page vs database), and a top-tier node may
      // not be persisted yet — so we send the kind the client already knows.
      const kind = nodesRef.current.get(id)?.kind
      let accepted: NotionNodeSelectionAccepted
      try {
        accepted = await apiFetch<NotionNodeSelectionAccepted>(
          `/api/integrations/notion/nodes/${encodeURIComponent(id)}/selection`,
          { method: "PATCH", body: JSON.stringify({ selected_for_sync: selected, kind }), signal },
          { expectedStatuses: [422, 502] }
        )
      } catch {
        // Aborted by reset()/unmount: the tree is being torn down, so leave state alone.
        if (signal.aborted) return
        rollback()
        clearResolving(id)
        setPendingCascades(c => Math.max(0, c - 1))
        return
      }

      // Seed from the 202 echo (counts may still be non-authoritative).
      patchNode(id, {
        selected_descendant_count: accepted.selected_descendant_count,
        total_descendant_count: accepted.total_descendant_count,
        counts_authoritative: accepted.counts_authoritative,
      })

      // Poll until terminal.
      const finish = () => {
        clearResolving(id)
        setPendingCascades(c => Math.max(0, c - 1))
        // Re-fetch children from the server so freshly-persisted selections
        // render correctly rather than from stale optimistic state.
        const node = nodesRef.current.get(id)
        if (node?.expanded) void fetchChildren(id, null, false)
      }

      // Poll until terminal or until the cap. A job that never resolves (lost
      // worker, unavailable record) must not loop forever and wedge the button.
      for (let polls = 0; polls < MAX_CASCADE_POLLS; polls++) {
        await new Promise(resolve => setTimeout(resolve, CASCADE_POLL_INTERVAL_MS))
        if (signal.aborted) return

        let poll: NotionSelectionStateResponse
        try {
          poll = await apiFetch<NotionSelectionStateResponse>(
            `/api/integrations/notion/nodes/${encodeURIComponent(id)}/selection`,
            { signal }
          )
        } catch {
          if (signal.aborted) return
          // Transient poll failure: keep the optimistic flip, stop resolving.
          finish()
          return
        }

        if (poll.state === "failed") {
          rollback()
          finish()
          return
        }
        if (poll.state === "done") {
          // Server counts win.
          if (poll.node) {
            patchNode(id, {
              selected_descendant_count: poll.node.selected_descendant_count,
              total_descendant_count: poll.node.total_descendant_count,
              counts_authoritative: poll.node.counts_authoritative,
            })
          }
          finish()
          return
        }
        // pending / running / null → keep polling.
      }

      // Cap reached without a terminal state: keep the optimistic flip (the job
      // may still finish server-side), but free the button and let the user know.
      finish()
      showFlash("Notion is still finishing that update in the background. Refresh to confirm.", "success")
    },
    [optimisticSetSubtree, clearResolving, patchNode, fetchChildren]
  )

  const toggleSelection = useCallback(
    (id: string, selected: boolean) => {
      const node = nodesRef.current.get(id)
      if (!node) return
      if (isFolder(node)) void toggleFolder(id, selected)
      else toggleLeaf(id, selected)
    },
    [toggleLeaf, toggleFolder]
  )

  // Mirror useNotionIntegration.disconnect: clear all tree state so it doesn't
  // leak across connections.
  const reset = useCallback(() => {
    cascadeAbortRef.current?.abort()
    cascadeAbortRef.current = null
    setNodesById(new Map())
    setTopIds([])
    topCursorRef.current = null
    setHasMore(false)
    setError(null)
    setPendingCascades(0)
  }, [])

  return {
    nodesById,
    topIds,
    loading,
    error,
    hasMore,
    loadingMore,
    loadMoreTop,
    toggleExpanded,
    toggleSelection,
    loadMoreChildren,
    retryChildren,
    reset,
    syncDisabled: pendingCascades > 0,
  }
}
