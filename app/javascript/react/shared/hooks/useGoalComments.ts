import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { insertComment, removeComment, updateComment, updateReactions } from "~/react/shared/commentThreads"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useReconnectCatchUp } from "~/react/shared/hooks/useReconnectCatchUp"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import { type ReactionType } from "~/react/shared/reactions"
import type { PaginatedResponse, ReactionUser, User } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

export type { ReactionUser }

export interface GoalComment {
  id: string
  content: string
  parent_id: string | null
  closed_at: string | null
  created_at: string
  updated_at: string
  user: User
  reactions: Record<string, ReactionUser[]>
  replies: GoalComment[]
}

interface GoalCommentListResponse extends PaginatedResponse {
  comments: GoalComment[]
}

export interface UseGoalCommentsResult {
  comments: GoalComment[]
  loading: boolean
  createComment: (content: string, parentId?: string) => Promise<void>
  editComment: (commentId: string, content: string) => Promise<void>
  deleteComment: (commentId: string) => Promise<void>
  closeThread: (commentId: string, closed?: boolean) => Promise<void>
  toggleReaction: (commentId: string, reactionType: ReactionType) => Promise<void>
}

export const goalCommentsQueryKey = (goalId: string) => ["goalComments", goalId] as const

// The cache holds the nested GoalComment[] the API returns (replies inline), which
// is what the pure helpers in shared/commentThreads operate on. Channel-first
// posture: the goal_comments channel is the freshness source, so no background
// refetch (see channelQueryDefaults).
export function goalCommentsQueryOptions(goalId: string) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: goalCommentsQueryKey(goalId),
    queryFn: async ({ signal }) => {
      const { comments } = await apiFetch<GoalCommentListResponse>(`/api/goals/${goalId}/comments`, { signal })
      return comments
    },
  })
}

const NO_COMMENTS: GoalComment[] = []

// Each mutation flashes its own failure, so the exposed wrappers swallow the
// rejection rather than making every caller handle it.
function swallow(promise: Promise<unknown>): Promise<void> {
  return promise.then(
    () => {},
    () => {}
  )
}

export function useGoalComments(goalId: string): UseGoalCommentsResult {
  const queryClient = useQueryClient()
  const query = useQuery(goalCommentsQueryOptions(goalId))

  const patch = useCallback(
    (fn: (list: GoalComment[]) => GoalComment[]) =>
      queryClient.setQueryData<GoalComment[]>(goalCommentsQueryKey(goalId), old => fn(old ?? [])),
    [queryClient, goalId]
  )

  const write = useCallback(
    (comments: GoalComment[]) => queryClient.setQueryData<GoalComment[]>(goalCommentsQueryKey(goalId), comments),
    [queryClient, goalId]
  )

  const createMutation = useMutation({
    mutationFn: ({ content, parentId }: { content: string; parentId?: string }) =>
      apiFetch<GoalComment>(`/api/goals/${goalId}/comments`, {
        method: "POST",
        body: JSON.stringify(parentId ? { content, parent_id: parentId } : { content }),
      }),
    onSuccess: comment => patch(list => insertComment(list, comment)),
    onError: () => showFlash("Couldn't post comment. Your text is preserved — try again."),
  })

  const editMutation = useMutation({
    mutationFn: ({ commentId, content }: { commentId: string; content: string }) =>
      apiFetch<GoalComment>(`/api/goals/${goalId}/comments/${commentId}`, {
        method: "PATCH",
        body: JSON.stringify({ content }),
      }),
    onSuccess: updated => patch(list => updateComment(list, updated)),
    onError: () => showFlash("Couldn't save comment edit."),
  })

  const deleteMutation = useMutation({
    mutationFn: (commentId: string) =>
      apiFetch(`/api/goals/${goalId}/comments/${commentId}`, { method: "DELETE" }).then(() => commentId),
    onSuccess: commentId => patch(list => removeComment(list, commentId)),
    onError: () => showFlash("Couldn't delete comment."),
  })

  // Closing or reopening a thread reshuffles which comments the panel shows, so
  // the endpoint answers with the whole list rather than the one row.
  const closeMutation = useMutation({
    mutationFn: ({ commentId, closed }: { commentId: string; closed: boolean }) =>
      apiFetch<GoalCommentListResponse>(`/api/goals/${goalId}/comments/${commentId}`, {
        method: "PATCH",
        body: JSON.stringify({ closed }),
      }),
    onSuccess: data => write(data.comments),
    onError: () => showFlash("Couldn't close thread."),
  })

  const reactionMutation = useMutation({
    mutationFn: ({ commentId, reactionType }: { commentId: string; reactionType: ReactionType }) =>
      apiFetch<GoalComment>(`/api/goals/${goalId}/comments/${commentId}/reactions?reaction_type=${reactionType}`, {
        method: "POST",
      }),
    onSuccess: updated => patch(list => updateComment(list, updated)),
    // Reaction toggle is low-stakes — next real-time update will sync state
  })

  const handleChannelMessage = useCallback(
    (action: ChannelEventAction, data: Record<string, unknown>) => {
      switch (action) {
        case ChannelEventAction.CREATED:
          patch(list => insertComment(list, data as unknown as GoalComment))
          break
        case ChannelEventAction.UPDATED:
          patch(list => updateComment(list, data as unknown as GoalComment))
          break
        case ChannelEventAction.DELETED:
          patch(list => removeComment(list, data.id as string))
          break
        case ChannelEventAction.REACTION_TOGGLED:
          patch(list =>
            updateReactions(list, data.comment_id as string, data.reactions as Record<string, ReactionUser[]>)
          )
          break
        // The panel-wide event carries the full list, so it patches like the
        // granular ones rather than invalidating — the payload is already the
        // answer a refetch would fetch.
        case ChannelEventAction.PANEL_UPDATED: {
          const incoming = data.comments as GoalComment[] | undefined
          if (incoming) write(incoming)
          break
        }
      }
    },
    [patch, write]
  )

  useChannel(
    { stream: ChannelStream.GOAL_COMMENTS, params: { goal_id: goalId } },
    ChannelEventResource.GOAL_COMMENT,
    handleChannelMessage
  )

  // Recover broadcasts missed while the popover was closed and its subscription
  // unwired — on socket reconnect and on a warm reopen. See useReconnectCatchUp.
  useReconnectCatchUp(goalCommentsQueryKey(goalId), "useGoalComments")

  const { mutateAsync: createMutate } = createMutation
  const { mutateAsync: editMutate } = editMutation
  const { mutateAsync: deleteMutate } = deleteMutation
  const { mutateAsync: closeMutate } = closeMutation
  const { mutateAsync: reactionMutate } = reactionMutation

  const createComment = useCallback(
    (content: string, parentId?: string) => swallow(createMutate({ content, parentId })),
    [createMutate]
  )
  const editComment = useCallback(
    (commentId: string, content: string) => swallow(editMutate({ commentId, content })),
    [editMutate]
  )
  const deleteComment = useCallback((commentId: string) => swallow(deleteMutate(commentId)), [deleteMutate])
  const closeThread = useCallback(
    (commentId: string, closed = true) => swallow(closeMutate({ commentId, closed })),
    [closeMutate]
  )
  const toggleReaction = useCallback(
    (commentId: string, reactionType: ReactionType) => swallow(reactionMutate({ commentId, reactionType })),
    [reactionMutate]
  )

  return {
    comments: query.data ?? NO_COMMENTS,
    loading: query.isLoading,
    createComment,
    editComment,
    deleteComment,
    closeThread,
    toggleReaction,
  }
}
