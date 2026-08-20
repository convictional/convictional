import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useRef } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel, type ChannelSubscriptionTarget } from "~/react/shared/hooks/useChannel"
import { useReconnectCatchUp } from "~/react/shared/hooks/useReconnectCatchUp"
import { commentIdFromHash, findCommentElement } from "~/react/shared/hooks/useScrollToHashComment"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import { type ReactionType } from "~/react/shared/reactions"
import type { PaginatedResponse, ReactionUser, User } from "~/react/shared/types"
import { ChannelEventAction, type ChannelEventResource } from "~/types/channels"
import type { CommentStoreApi } from "./CommentStoreContext"

export type { ReactionUser }

export interface Comment {
  id: string
  // GlobalID used to anchor a Decision to this comment across resources.
  global_id: string
  content: string
  quoted_text: string
  comment_mark_id: string
  resolved_at: string | null
  created_at: string
  user: User
  reactions: Record<string, ReactionUser[]>
}

export interface CommentMarkListResponse extends PaginatedResponse {
  comments: Comment[]
}

export interface CommentThreadResponse {
  comment_mark_id: string
  resolved_at: string | null
  comments: Comment[]
}

export interface CommentThread {
  markId: string
  comments: Comment[]
}

export function groupIntoThreads(comments: Comment[]): CommentThread[] {
  const map = new Map<string, Comment[]>()
  for (const c of comments) {
    const existing = map.get(c.comment_mark_id)
    if (existing) {
      existing.push(c)
    } else {
      map.set(c.comment_mark_id, [c])
    }
  }
  return Array.from(map.entries()).map(([markId, comments]) => ({ markId, comments }))
}

export const commentThreadsQueryKey = (resourceId: string) => ["comments", resourceId] as const

// The cache holds the flat Comment[] the API returns; groupIntoThreads is the
// `select` so subscribers receive CommentThread[]. Channel patches and mutations
// therefore operate on the flat list (add/update/remove a comment by id) and the
// grouping is recomputed on read. currentUser-style channel-first posture: the
// channel is the freshness source, so no background refetch (see channelQueryDefaults).
export function commentThreadsQueryOptions(commentsPath: (resourceId: string) => string, resourceId: string) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: commentThreadsQueryKey(resourceId),
    queryFn: async () => {
      const { comments } = await apiFetch<CommentMarkListResponse>(commentsPath(resourceId))
      return comments
    },
    select: groupIntoThreads,
  })
}

// --- Pure cache-patch helpers (operate on the flat Comment[] cache value) ---

export function addCommentToList(list: Comment[] | undefined, comment: Comment): Comment[] {
  const current = list ?? []
  // Dedup: an optimistic create already inserted this comment, so its echoed
  // CREATED channel event is a no-op.
  if (current.some(c => c.id === comment.id)) return current
  return [...current, comment]
}

export function updateCommentInList(list: Comment[] | undefined, comment: Comment): Comment[] {
  return (list ?? []).map(c => (c.id === comment.id ? comment : c))
}

export function removeCommentFromList(list: Comment[] | undefined, commentId: string): Comment[] {
  return (list ?? []).filter(c => c.id !== commentId)
}

export function setReactionsInList(
  list: Comment[] | undefined,
  commentId: string,
  reactions: Record<string, ReactionUser[]>
): Comment[] {
  return (list ?? []).map(c => (c.id === commentId ? { ...c, reactions } : c))
}

// Apply a resolve/reopen for a whole thread (mark). When resolvedAt is set the
// thread is gone, so drop every comment on that mark; otherwise replace the
// mark's comments with the server's latest. Empty `comments` with no resolve is
// a no-op (mirrors resolveThreadFromEvent's length-0 guard).
export function applyResolvedThread(
  list: Comment[] | undefined,
  markId: string,
  comments: Comment[],
  resolvedAt: string | null
): Comment[] {
  const current = list ?? []
  if (resolvedAt) return current.filter(c => c.comment_mark_id !== markId)
  if (comments.length === 0) return current
  return [...current.filter(c => c.comment_mark_id !== markId), ...comments]
}

export function toggleReactionInList(
  list: Comment[] | undefined,
  commentId: string,
  reactionType: ReactionType,
  userId: string,
  userName: string
): Comment[] {
  return (list ?? []).map(c => {
    if (c.id !== commentId) return c
    const users = c.reactions[reactionType] ?? []
    const hasReacted = users.some(u => u.id === userId)
    const nextUsers = hasReacted
      ? users.filter(u => u.id !== userId)
      : [...users, { id: userId, display_name: userName }]
    const nextReactions = { ...c.reactions, [reactionType]: nextUsers }
    if (nextUsers.length === 0) delete nextReactions[reactionType]
    return { ...c, reactions: nextReactions }
  })
}

// --- The hook ---

export interface CommentThreadsApi {
  threads: CommentThread[]
  // Query has settled with data at least once. Gates Yjs orphan-mark cleanup:
  // while loading (no data) or on error, the sidebar may be empty but the doc
  // can already hold valid marks restored from Yjs — cleaning up then would
  // strip them. This replaces the old `loadedFor === resourceId` guard.
  isLoaded: boolean
  createComment: (content: string, quotedText: string, commentMarkId: string) => Promise<Comment>
  editComment: (commentId: string, content: string) => Promise<void>
  deleteComment: (commentId: string) => Promise<void>
  resolveThread: (commentId: string, resolved?: boolean) => Promise<void>
  toggleReaction: (commentId: string, reactionType: ReactionType) => Promise<void>
  // Force-refetch and resolve only once the fresh comments are in the cache.
  // refetchQueries (not invalidateQueries) because useCommentMarks awaits this
  // before clearing its in-flight mark protection — invalidate resolves when the
  // refetch *starts*, dropping protection before the new threads land.
  refetchComments: () => Promise<void>
  // Imperative read of the current threads for callers that need the value at an
  // event (not a subscription), e.g. CommentThread checking whether a deleted
  // thread is gone before removing its editor mark.
  getThreads: () => CommentThread[]
}

export interface CommentThreadsConfig {
  commentsPath: (resourceId: string) => string
  resourceId: string
  channel: ChannelSubscriptionTarget
  commentResource: ChannelEventResource.DOCUMENT_COMMENT | ChannelEventResource.POST_DRAFT_COMMENT
  // The slim UI store instance, used for the few reads/resets that ride a server
  // event: the current user's identity for optimistic reactions, closing the
  // editing state on a successful edit, and applying the deep-link selection.
  // (Clearing a vanished selection lives in the UI layer — see
  // useClearActiveCommentWhenGone.) Passed in rather than read from context so the
  // hook can run above the CommentStoreProvider in the editor body.
  uiStore: CommentStoreApi
}

const EMPTY_THREADS: CommentThread[] = []

// A deep link opens the editor and its comments query in parallel with the Yjs
// content sync that renders the comment marks, so the target mark can be absent
// from the DOM when the threads first load. Retry the scroll across this many
// animation frames (~5s at 60fps) waiting for the mark to render before giving
// up; the active-comment highlight still applies whenever the mark appears.
const DEEP_LINK_SCROLL_MAX_FRAMES = 300

export function useCommentThreads({
  commentsPath,
  resourceId,
  channel,
  commentResource,
  uiStore,
}: CommentThreadsConfig): CommentThreadsApi {
  const queryClient = useQueryClient()
  const query = useQuery(commentThreadsQueryOptions(commentsPath, resourceId))

  const readList = () => queryClient.getQueryData<Comment[]>(commentThreadsQueryKey(resourceId))
  const writeList = (next: Comment[]) => queryClient.setQueryData<Comment[]>(commentThreadsQueryKey(resourceId), next)
  // Patch the cache through a pure list helper. The non-clearing updates (create,
  // edit, reaction) share this between their mutation onSuccess and their channel
  // handler, so the two paths spell the same one-liner.
  const patchList = (fn: (list: Comment[] | undefined) => Comment[]) =>
    queryClient.setQueryData<Comment[]>(commentThreadsQueryKey(resourceId), fn)

  const createMutation = useMutation({
    mutationFn: ({
      content,
      quotedText,
      commentMarkId,
    }: {
      content: string
      quotedText: string
      commentMarkId: string
    }) =>
      apiFetch<Comment>(commentsPath(resourceId), {
        method: "POST",
        body: JSON.stringify({ content, quoted_text: quotedText, comment_mark_id: commentMarkId }),
      }),
    onSuccess: comment => {
      patchList(old => addCommentToList(old, comment))
    },
  })

  const editMutation = useMutation({
    mutationFn: ({ commentId, content }: { commentId: string; content: string }) =>
      apiFetch<Comment>(`${commentsPath(resourceId)}/${commentId}`, {
        method: "PATCH",
        body: JSON.stringify({ content }),
      }),
    onSuccess: updated => {
      patchList(old => updateCommentInList(old, updated))
      uiStore.getState().setEditingComment(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (commentId: string) => apiFetch(`${commentsPath(resourceId)}/${commentId}`, { method: "DELETE" }),
    onSuccess: (_data, commentId) => {
      writeList(removeCommentFromList(readList(), commentId))
    },
  })

  const resolveMutation = useMutation({
    mutationFn: ({ commentId, resolved }: { commentId: string; resolved: boolean }) =>
      apiFetch<CommentThreadResponse>(`${commentsPath(resourceId)}/${commentId}`, {
        method: "PATCH",
        body: JSON.stringify({ resolved }),
      }),
    onSuccess: thread => {
      writeList(applyResolvedThread(readList(), thread.comment_mark_id, thread.comments, thread.resolved_at))
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ commentId, reactionType }: { commentId: string; reactionType: ReactionType }) =>
      apiFetch<Comment>(`${commentsPath(resourceId)}/${commentId}/reactions?reaction_type=${reactionType}`, {
        method: "POST",
      }),
    onMutate: async ({ commentId, reactionType }) => {
      // Stop an in-flight channel-driven refetch from racing the optimistic write.
      await queryClient.cancelQueries({ queryKey: commentThreadsQueryKey(resourceId) })
      const previous = readList()
      const { currentUserId, currentUserName } = uiStore.getState()
      patchList(old => toggleReactionInList(old, commentId, reactionType, currentUserId, currentUserName))
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(commentThreadsQueryKey(resourceId), context.previous)
    },
    onSuccess: (updated, { commentId }) => {
      patchList(old => setReactionsInList(old, commentId, updated.reactions))
    },
  })

  // Channel events patch the cache (granular CREATED/UPDATED/DELETED/RESOLVED/
  // REACTION_TOGGLED carry the full row, so no network round-trip). The channel
  // is the freshness source for this query.
  useChannel(channel, commentResource, (action, data) => {
    if (action === ChannelEventAction.CREATED) {
      patchList(old => addCommentToList(old, data as unknown as Comment))
    } else if (action === ChannelEventAction.UPDATED) {
      patchList(old => updateCommentInList(old, data as unknown as Comment))
    } else if (action === ChannelEventAction.DELETED) {
      writeList(removeCommentFromList(readList(), data.id as string))
    } else if (action === ChannelEventAction.RESOLVED) {
      // send_resolved (streams.py) broadcasts comment_mark_id + comments only, no
      // top-level resolved_at — so read it off the payload's comments, where every
      // comment in a resolved thread shares the same value. If the backend ever
      // adds a top-level resolved_at, prefer it here to drop the comments[0] hop.
      const comments = data.comments as unknown as Comment[]
      writeList(
        applyResolvedThread(readList(), data.comment_mark_id as string, comments, comments[0]?.resolved_at ?? null)
      )
    } else if (action === ChannelEventAction.REACTION_TOGGLED) {
      patchList(old =>
        setReactionsInList(old, data.comment_id as string, data.reactions as Record<string, ReactionUser[]>)
      )
    }
  })

  // Recover broadcasts missed while this island was unmounted and its subscription
  // unwired — on socket reconnect and on a warm remount. See useReconnectCatchUp.
  useReconnectCatchUp(commentThreadsQueryKey(resourceId), "useCommentThreads")

  // Activate and scroll to a comment thread from the URL hash (deep link from a
  // notification email) once, after the comments first load. Activating opens the
  // thread's card and highlights its mark (see CommentSystem); the scroll brings
  // the mark into view — without it the editor lands at the top of the document
  // and the comment stays off-screen (issue #8825). The mark renders from the Yjs
  // doc, which can sync after the comments query resolves, so the scroll retries
  // across frames until the mark element exists.
  const deepLinkAppliedRef = useRef(false)
  const deepLinkFrameRef = useRef(0)
  useEffect(() => {
    if (deepLinkAppliedRef.current) return
    const threads = query.data
    if (!threads) return
    const commentId = commentIdFromHash(window.location.hash)
    if (!commentId) return
    const thread = threads.find(t => t.comments.some(c => c.id === commentId))
    if (!thread) return
    deepLinkAppliedRef.current = true
    const { markId } = thread
    uiStore.getState().setActiveComment(markId)

    let framesLeft = DEEP_LINK_SCROLL_MAX_FRAMES
    const tryScroll = () => {
      const el = findCommentElement(markId)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" })
      } else if (framesLeft-- > 0) {
        deepLinkFrameRef.current = requestAnimationFrame(tryScroll)
      }
    }
    deepLinkFrameRef.current = requestAnimationFrame(tryScroll)
    // No cleanup here: this effect re-runs on every query.data change (e.g. a
    // mark-detection refetch), and cancelling the pending retry then would abort
    // the scroll before the mark rendered. The retry is cancelled only on unmount.
  }, [query.data, uiStore])

  useEffect(() => () => cancelAnimationFrame(deepLinkFrameRef.current), [])

  // Stable identities so the returned object (the CommentThreadsProvider value)
  // changes only when the threads themselves change. Without this, every editor-
  // body render would recreate the context value and re-render all comment
  // consumers. mutateAsync and queryClient are referentially stable across
  // renders, so they're the only dependencies these wrappers need.
  const { mutateAsync: createMutate } = createMutation
  const { mutateAsync: editMutate } = editMutation
  const { mutateAsync: deleteMutate } = deleteMutation
  const { mutateAsync: resolveMutate } = resolveMutation
  const { mutateAsync: toggleMutate } = toggleMutation

  const createComment = useCallback(
    (content: string, quotedText: string, commentMarkId: string) =>
      createMutate({ content, quotedText, commentMarkId }),
    [createMutate]
  )
  const editComment = useCallback(
    (commentId: string, content: string) => editMutate({ commentId, content }).then(() => {}),
    [editMutate]
  )
  const deleteComment = useCallback((commentId: string) => deleteMutate(commentId).then(() => {}), [deleteMutate])
  const resolveThread = useCallback(
    (commentId: string, resolved = true) => resolveMutate({ commentId, resolved }).then(() => {}),
    [resolveMutate]
  )
  const toggleReaction = useCallback(
    (commentId: string, reactionType: ReactionType) =>
      // onError already restores the snapshot; swallow so callers don't see a reject.
      toggleMutate({ commentId, reactionType }).then(
        () => {},
        () => {}
      ),
    [toggleMutate]
  )
  const refetchComments = useCallback(
    () => queryClient.refetchQueries({ queryKey: commentThreadsQueryKey(resourceId) }).then(() => {}),
    [queryClient, resourceId]
  )
  const getThreads = useCallback(
    () => groupIntoThreads(queryClient.getQueryData<Comment[]>(commentThreadsQueryKey(resourceId)) ?? []),
    [queryClient, resourceId]
  )

  return useMemo(
    () => ({
      threads: query.data ?? EMPTY_THREADS,
      isLoaded: query.isSuccess,
      createComment,
      editComment,
      deleteComment,
      resolveThread,
      toggleReaction,
      refetchComments,
      getThreads,
    }),
    [
      query.data,
      query.isSuccess,
      createComment,
      editComment,
      deleteComment,
      resolveThread,
      toggleReaction,
      refetchComments,
      getThreads,
    ]
  )
}
