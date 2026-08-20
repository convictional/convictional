import type { ReactElement } from "react"
import { vi } from "vitest"

import { render as baseRender } from "../../shared/testUtils"
import {
  CommentStoreProvider,
  type CommentStoreApi,
} from "../../../../../app/javascript/react/composites/editor/features/comments/CommentStoreContext"
import { CommentThreadsProvider } from "../../../../../app/javascript/react/composites/editor/features/comments/CommentThreadsContext"
import type {
  Comment,
  CommentThread,
  CommentThreadsApi,
} from "../../../../../app/javascript/react/composites/editor/features/comments/commentThreads"
import { documentCommentUIStore } from "../../../../../app/javascript/react/features/documentEditor/store"

export const makeComment = (overrides: Partial<Comment> = {}): Comment => ({
  id: "c1",
  global_id: "gid://convictional/DocumentComment/c1",
  content: "hello",
  quoted_text: "some text",
  comment_mark_id: "mark-1",
  resolved_at: null,
  created_at: "2026-01-01T00:00:00Z",
  user: { id: "u1", display_name: "Alice", picture: null },
  reactions: {},
  ...overrides,
})

// A stub CommentThreadsApi for component tests: server state and mutations come
// from here, not from the UI store. Pass `threads` to seed the rendered list
// (getThreads mirrors it); pass any mutation to assert it was called.
export function buildThreadsApi(overrides: Partial<CommentThreadsApi> = {}): CommentThreadsApi {
  const threads = overrides.threads ?? []
  return {
    threads,
    isLoaded: overrides.isLoaded ?? true,
    createComment: overrides.createComment ?? vi.fn().mockResolvedValue(makeComment()),
    editComment: overrides.editComment ?? vi.fn().mockResolvedValue(undefined),
    deleteComment: overrides.deleteComment ?? vi.fn().mockResolvedValue(undefined),
    resolveThread: overrides.resolveThread ?? vi.fn().mockResolvedValue(undefined),
    toggleReaction: overrides.toggleReaction ?? vi.fn().mockResolvedValue(undefined),
    refetchComments: overrides.refetchComments ?? vi.fn().mockResolvedValue(undefined),
    getThreads: overrides.getThreads ?? (() => threads),
  }
}

interface RenderOptions {
  uiStore?: CommentStoreApi
  threadsApi?: CommentThreadsApi
}

export function renderWithCommentProviders(
  ui: ReactElement,
  { uiStore = documentCommentUIStore, threadsApi = buildThreadsApi() }: RenderOptions = {}
) {
  // baseRender wraps in the singleton QueryClientProvider (mirrors production
  // roots) so any nested useQuery — e.g. DecisionMarker — resolves.
  return baseRender(
    <CommentStoreProvider value={uiStore}>
      <CommentThreadsProvider value={threadsApi}>{ui}</CommentThreadsProvider>
    </CommentStoreProvider>
  )
}

export type { Comment, CommentThread, CommentThreadsApi }
