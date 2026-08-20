import { createContext, useContext } from "react"
import { useStore, type StoreApi } from "zustand"

import type { CommentUIStore } from "./createCommentUIStore"

export type CommentStoreApi = StoreApi<CommentUIStore>

const CommentStoreContext = createContext<CommentStoreApi | null>(null)

export const CommentStoreProvider = CommentStoreContext.Provider

export function useCommentStore<T>(selector: (s: CommentUIStore) => T): T {
  const store = useContext(CommentStoreContext)
  if (!store) throw new Error("useCommentStore must be used within a CommentStoreProvider")
  return useStore(store, selector)
}

export function useCommentStoreApi(): CommentStoreApi {
  const store = useContext(CommentStoreContext)
  if (!store) throw new Error("useCommentStoreApi must be used within a CommentStoreProvider")
  return store
}
