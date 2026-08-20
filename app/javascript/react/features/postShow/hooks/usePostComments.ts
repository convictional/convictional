import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { insertComment, removeComment, updateComment, updateReactions } from "~/react/shared/commentThreads"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useReconnectCatchUp } from "~/react/shared/hooks/useReconnectCatchUp"
import { type ReactionType } from "~/react/shared/reactions"
import type { PostComment, ReactionUser } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

import {
  commentInTree,
  postCommentsQueryKey,
  postCommentsQueryOptions,
  splitPostComments,
  toggleReactionInTree,
} from "../queries"

interface CreateCommentOptions {
  parentId?: string
  // The composer's attachment claim id; the server claims any uploads staged
  // under it onto the new comment. `unfurlLinks` is server-default-on; pass
  // false only when the composer's "remove preview" affordance was used.
  attachmentClaimId?: string
  unfurlLinks?: boolean
}

interface EditCommentOptions {
  attachmentClaimId?: string
  unfurlLinks?: boolean
}

export interface UsePostCommentsOptions {
  postId: string
  // The viewer's id, used to suppress the "new comments" indicator for their own
  // comments — the broadcast has no author-skip, so a tab receives CREATED for
  // comments it (or another tab of the same user) authored.
  currentUserId: string
  initial: PostComment[]
  // The post body comment. Rendered separately by PostBody, but its reactions
  // and cross-tab updates flow through the same channel, so it lives in the same
  // cache and its id splits the cache into original vs top-level.
  initialOriginal: PostComment | null
  // Fired when a genuinely new comment from another user arrives over the channel
  // (not one this tab already had, and not the viewer's own). Drives the "new
  // comments" indicator.
  onRemoteCreate?: (comment: PostComment) => void
}

export interface UsePostCommentsResult {
  original: PostComment | null
  topLevel: PostComment[]
  loading: boolean
  fetch: () => Promise<void>
  createComment: (content: string, options?: CreateCommentOptions) => Promise<PostComment | null>
  editComment: (commentId: string, content: string, options?: EditCommentOptions) => Promise<PostComment | null>
  deleteComment: (commentId: string) => Promise<void>
  toggleReaction: (commentId: string, reactionType: ReactionType) => void
  // Optimistically reflect a post-body content edit (PATCH /posts/{id} returns
  // Post, not the comment, so the new body content comes from the editor).
  setOriginalContent: (content: string) => void
}

export function usePostComments({
  postId,
  currentUserId,
  initial,
  initialOriginal,
  onRemoteCreate,
}: UsePostCommentsOptions): UsePostCommentsResult {
  const queryClient = useQueryClient()
  const { user } = useCurrentUser()
  // The original's id is stable for the life of the post (an edit replaces its
  // content, not its id), so the prop carries it — no need to read the live query.
  const originalId = initialOriginal?.id

  // Seed the cache with the detail response's comments (the show response already
  // bundles them) so first paint costs no comment fetch, PostBody/the list render
  // with no flash, and — crucially — channel patches and mutations build on the
  // real tree from the first frame (they setQueryData off the cached list, so an
  // unseeded cache would drop the bundled comments on the first patch). initialData,
  // NOT placeholderData, because placeholderData renders but is never written to
  // the cache. One consequence: the seed makes the cache non-empty on the cold
  // first mount, so the remount catch-up below also fires once there — a background
  // refresh (no flash) that keeps the channel-backed cache authoritative.
  const query = useQuery({
    ...postCommentsQueryOptions(postId, originalId),
    initialData: initialOriginal ? [...initial, initialOriginal] : initial,
    // Stable per originalId so React Query memoizes the split result across
    // renders — the same referential stability selectDecisions gives.
    select: useCallback((comments: PostComment[]) => splitPostComments(comments, originalId), [originalId]),
  })

  const { original, topLevel } = query.data ?? { original: initialOriginal, topLevel: initial }

  // Patch the cache through a pure tree helper. Both a mutation's onSuccess and
  // the channel handler spell the same one-liner, so the two paths stay identical.
  const patchComments = useCallback(
    (fn: (list: PostComment[]) => PostComment[]) =>
      queryClient.setQueryData<PostComment[]>(postCommentsQueryKey(postId), old => fn(old ?? [])),
    [queryClient, postId]
  )

  const createMutation = useMutation({
    mutationFn: ({ content, options }: { content: string; options: CreateCommentOptions }) => {
      const body: Record<string, unknown> = { content }
      if (options.parentId) body.parent_id = options.parentId
      if (options.attachmentClaimId) body.attachment_claim_id = options.attachmentClaimId
      if (options.unfurlLinks === false) body.unfurl_links = false
      return apiFetch<PostComment>(`/api/posts/${postId}/comments`, { method: "POST", body: JSON.stringify(body) })
    },
    onSuccess: comment => {
      patchComments(list => (commentInTree(list, comment.id) ? list : insertComment(list, comment)))
    },
  })

  const editMutation = useMutation({
    mutationFn: ({
      commentId,
      content,
      options,
    }: {
      commentId: string
      content: string
      options: EditCommentOptions
    }) => {
      const body: Record<string, unknown> = { content }
      if (options.attachmentClaimId) body.attachment_claim_id = options.attachmentClaimId
      if (options.unfurlLinks === false) body.unfurl_links = false
      return apiFetch<PostComment>(`/api/posts/${postId}/comments/${commentId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      })
    },
    onSuccess: updated => {
      patchComments(list => updateComment(list, updated))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (commentId: string) => apiFetch(`/api/posts/${postId}/comments/${commentId}`, { method: "DELETE" }),
    onSuccess: (_data, commentId) => {
      patchComments(list => removeComment(list, commentId))
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ commentId, reactionType }: { commentId: string; reactionType: ReactionType }) =>
      apiFetch<PostComment>(`/api/posts/${postId}/comments/${commentId}/reactions?reaction_type=${reactionType}`, {
        method: "POST",
      }),
    onMutate: async ({ commentId, reactionType }) => {
      // Stop an in-flight channel-driven refetch from racing the optimistic write.
      await queryClient.cancelQueries({ queryKey: postCommentsQueryKey(postId) })
      const previous = queryClient.getQueryData<PostComment[]>(postCommentsQueryKey(postId))
      const reactor: ReactionUser = { id: currentUserId, display_name: user?.display_name ?? "" }
      patchComments(list => toggleReactionInTree(list, commentId, reactionType, reactor))
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(postCommentsQueryKey(postId), context.previous)
    },
    onSuccess: (updated, { commentId }) => {
      // Merge only reactions, never the whole comment: the toggle response carries
      // a transient bumped updated_at (server auto_now in memory, not persisted)
      // that would otherwise flip the "(edited)" indicator. Mirrors REACTION_TOGGLED.
      patchComments(list => updateReactions(list, commentId, updated.reactions))
    },
  })

  const { mutateAsync: createMutate } = createMutation
  const { mutateAsync: editMutate } = editMutation
  const { mutateAsync: deleteMutate } = deleteMutation
  const { mutate: toggleMutate } = toggleMutation

  const createComment = useCallback(
    async (content: string, options: CreateCommentOptions = {}) => {
      try {
        return await createMutate({ content, options })
      } catch {
        showFlash("Couldn't post comment. Your text is preserved — try again.")
        return null
      }
    },
    [createMutate]
  )

  const editComment = useCallback(
    async (commentId: string, content: string, options: EditCommentOptions = {}) => {
      try {
        return await editMutate({ commentId, content, options })
      } catch {
        showFlash("Couldn't save comment edit.")
        return null
      }
    },
    [editMutate]
  )

  const deleteComment = useCallback(
    async (commentId: string) => {
      try {
        await deleteMutate(commentId)
      } catch {
        showFlash("Couldn't delete comment.")
      }
    },
    [deleteMutate]
  )

  // Fire-and-forget: onMutate applies the reaction optimistically and onError
  // rolls back, so callers never see a rejection (mutate, not mutateAsync).
  const toggleReaction = useCallback(
    (commentId: string, reactionType: ReactionType) => {
      toggleMutate({ commentId, reactionType })
    },
    [toggleMutate]
  )

  const setOriginalContent = useCallback(
    (content: string) => {
      patchComments(list => {
        const orig = list.find(c => c.id === originalId)
        return orig ? updateComment(list, { ...orig, content }) : list
      })
    },
    [patchComments, originalId]
  )

  // Force-refetch and resolve only once the fresh list is in the cache (a caller
  // awaiting it wants the fresh comments in hand). Mirrors refetchComments.
  const fetch = useCallback(
    () => queryClient.refetchQueries({ queryKey: postCommentsQueryKey(postId) }).then(() => {}),
    [queryClient, postId]
  )

  // Channel events patch the cache (granular CREATED/UPDATED/DELETED/REACTION_TOGGLED
  // carry the full row, so no network round-trip). The channel is the freshness
  // source. Armed unconditionally — postId is always present. The inline handler
  // reads the latest currentUserId/onRemoteCreate (useChannel refreshes its
  // callback ref every render), so no per-value refs are needed.
  useChannel(
    { stream: ChannelStream.POST_COMMENTS, params: { post_id: postId } },
    ChannelEventResource.POST_COMMENT,
    (action, data) => {
      switch (action) {
        case ChannelEventAction.CREATED: {
          const comment = data as unknown as PostComment
          const list = queryClient.getQueryData<PostComment[]>(postCommentsQueryKey(postId)) ?? []
          if (commentInTree(list, comment.id)) break
          // The viewer's own comment (this tab inserted it, or another tab of
          // theirs authored it) must not raise the "new comments" indicator.
          if (comment.user.id !== currentUserId) onRemoteCreate?.(comment)
          patchComments(l => (commentInTree(l, comment.id) ? l : insertComment(l, comment)))
          break
        }
        case ChannelEventAction.UPDATED: {
          patchComments(list => updateComment(list, data as unknown as PostComment))
          break
        }
        case ChannelEventAction.DELETED: {
          patchComments(list => removeComment(list, data.id as string))
          break
        }
        case ChannelEventAction.REACTION_TOGGLED: {
          const commentId = data.comment_id as string
          const reactions = data.reactions as Record<string, ReactionUser[]>
          patchComments(list => updateReactions(list, commentId, reactions))
          break
        }
      }
    }
  )

  // Recover broadcasts missed while this island was unmounted and its subscription
  // unwired — on socket reconnect and on a warm remount. See useReconnectCatchUp.
  // initialData seeds the cache, so the warm-remount refresh also fires once on the
  // cold first mount — a background refresh, not a flash (the seed is rendered).
  useReconnectCatchUp(postCommentsQueryKey(postId), "usePostComments")

  return {
    original,
    topLevel,
    loading: query.isLoading,
    fetch,
    createComment,
    editComment,
    deleteComment,
    toggleReaction,
    setOriginalContent,
  }
}
