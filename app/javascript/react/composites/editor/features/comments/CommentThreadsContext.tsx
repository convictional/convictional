import { createContext, useContext } from "react"

import type { CommentThreadsApi } from "./commentThreads"

const CommentThreadsContext = createContext<CommentThreadsApi | null>(null)

export const CommentThreadsProvider = CommentThreadsContext.Provider

// Server-state side of the comment system: the threads cache plus the mutations
// and channel patches that keep it live (see useCommentThreads). The UI side
// (selection, card position, drafts) stays in the Zustand CommentStoreContext.
export function useCommentThreadsContext(): CommentThreadsApi {
  const ctx = useContext(CommentThreadsContext)
  if (!ctx) throw new Error("useCommentThreadsContext must be used within a CommentThreadsProvider")
  return ctx
}
