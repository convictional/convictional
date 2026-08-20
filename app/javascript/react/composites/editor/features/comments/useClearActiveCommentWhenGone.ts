import { useEffect } from "react"

import type { CommentStoreApi } from "./CommentStoreContext"
import type { CommentThread } from "./commentThreads"

// UI-layer reaction to server state: when the selected thread disappears (deleted
// or resolved, by this tab or another), drop the selection. Kept out of
// useCommentThreads so data flows one way — the threads cache drives the UI, not
// the reverse. Covers every removal path uniformly because it watches the derived
// list rather than each mutation/channel handler.
export function useClearActiveCommentWhenGone(threads: CommentThread[], uiStore: CommentStoreApi): void {
  useEffect(() => {
    const active = uiStore.getState().activeCommentId
    if (active && !threads.some(t => t.markId === active)) {
      uiStore.getState().setActiveComment(null)
    }
  }, [threads, uiStore])
}
