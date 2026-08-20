import { useEditorEffect, useEditorState } from "@handlewithcare/react-prosemirror"
import type { EditorView } from "prosemirror-view"
import { useEffect, useRef, useState } from "react"

import { getCommentMarkIds } from "~/richText/schema/commentMark"
import { useCommentStore } from "./CommentStoreContext"
import { type CommentThread } from "./commentThreads"
import { useCommentThreadsContext } from "./CommentThreadsContext"

export function cleanupOrphanMarks(
  view: EditorView,
  threads: CommentThread[],
  pendingCommentId: string | null,
  pendingMarkIds?: Set<string>
): void {
  const markType = view.state.schema.marks.comment
  if (!markType) return

  const validIds = new Set(threads.map(t => t.markId))
  if (pendingCommentId) validIds.add(pendingCommentId)
  if (pendingMarkIds) {
    for (const id of pendingMarkIds) validIds.add(id)
  }

  let tr = view.state.tr
  view.state.doc.descendants((node, pos) => {
    for (const mark of node.marks) {
      if (mark.type === markType && !validIds.has(mark.attrs.commentId as string)) {
        tr = tr.removeMark(pos, pos + node.nodeSize, mark)
      }
    }
  })

  if (tr.docChanged) view.dispatch(tr)
}

export function useCommentMarks() {
  const { threads, refetchComments, isLoaded, getThreads } = useCommentThreadsContext()
  const pendingCommentId = useCommentStore(s => s.pendingCommentId)
  const fetchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const knownMarkIdsRef = useRef(new Set<string>())
  const pendingFetchMarkIdsRef = useRef(new Set<string>())
  // react-query structural sharing keeps `threads` referentially stable across a
  // no-op refetch, so a state tick is needed to re-run the cleanup effect.
  const [cleanupTick, setCleanupTick] = useState(false)

  // The mark-detection effect below must re-run on every doc change (marks arrive
  // from a live paste or Yjs sync). useEditorEffect only re-runs when its deps
  // change, and the EditorView reference is stable across transactions, so a bare
  // useEditorState() re-render is not enough — we depend on editorState.doc, a
  // fresh object per doc-changing transaction, to trigger the effect.
  const editorState = useEditorState()

  // Detect new marks from Yjs sync and fetch comments if needed
  useEditorEffect(
    view => {
      const currentIds = getCommentMarkIds(view.state.doc)
      const threadIds = new Set(threads.map(t => t.markId))

      let hasNew = false
      for (const id of currentIds) {
        if (!threadIds.has(id) && !knownMarkIdsRef.current.has(id) && id !== pendingCommentId) {
          pendingFetchMarkIdsRef.current.add(id)
          hasNew = true
        }
      }
      knownMarkIdsRef.current = currentIds

      if (hasNew) {
        if (fetchTimerRef.current) clearTimeout(fetchTimerRef.current)
        fetchTimerRef.current = setTimeout(() => {
          const idsToFetch = new Set(pendingFetchMarkIdsRef.current)
          refetchComments()
            .then(() => {
              for (const id of idsToFetch) pendingFetchMarkIdsRef.current.delete(id)
              setCleanupTick(t => !t)
            })
            .catch(() => {})
        }, 500)
      }
    },
    [editorState.doc, threads, pendingCommentId, refetchComments]
  )

  // Cancel a pending debounce on unmount only. The timer fires refetchComments()
  // against the module-singleton queryClient, which outlives this island — without
  // this, a navigation away within the 500 ms window fires a stale
  // request for the resource the user just left. Unmount-only (not deps-tied) so
  // the debounce above isn't reset on every render when threads/pendingCommentId
  // change.
  useEffect(
    () => () => {
      if (fetchTimerRef.current) clearTimeout(fetchTimerRef.current)
    },
    []
  )

  // Skip cleanup until the comments query has loaded for the current resource.
  // While loading (no data) or on error, threads is [] but the doc may already
  // have valid marks restored from Yjs or IndexedDB — running cleanup here would
  // strip them and broadcast the deletion to all peers via the CRDT. isLoaded is
  // the query's success state (false on error); a failed load keeps the marks
  // and shows an empty sidebar.
  //
  // Read the valid threads imperatively via getThreads() (live cache) rather than
  // the rendered `threads` prop: after createComment, onSuccess patches the cache
  // and only then does closeCommentCard clear pendingCommentId, re-running this
  // effect — but the `threads` prop still lags the cache by a render, so it would
  // not yet contain the just-created thread. Using the stale prop here treats the
  // fresh mark as an orphan and strips it (the comment "disappears"). The cache is
  // already current at this point, so the live read keeps the mark. `threads` stays
  // in the deps to re-run cleanup whenever the thread set changes.
  useEditorEffect(
    view => {
      if (!isLoaded) return
      cleanupOrphanMarks(view, getThreads(), pendingCommentId, pendingFetchMarkIdsRef.current)
    },
    [threads, pendingCommentId, isLoaded, getThreads, cleanupTick]
  )
}
