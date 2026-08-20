import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { apiFetch } from "~/react/shared/apiFetch"
import { insertInOrder, mergeDedup } from "~/react/shared/chatMessageOrdering"
import { useCatchUpMessages } from "~/react/shared/hooks/useCatchUpMessages"
import { useChatChannel } from "~/react/shared/hooks/useChatChannel"
import { useChatMessageSubscription } from "~/react/shared/hooks/useChatMessageSubscription"
import { useLinkPreviewUnfurl } from "~/react/shared/hooks/useLinkPreviewUnfurl"
import { useMailboxEntryReadTracking } from "~/react/shared/hooks/useMailboxEntryReadTracking"
import { useReactionToggle } from "~/react/shared/hooks/useReactionToggle"
import { useTypingBroadcast } from "~/react/shared/hooks/useTypingBroadcast"
import type { ChatMessage, MessageListResponse, MessageWindowResponse, ReplyPreview, User } from "~/react/shared/types"
import { isBlankMarkdown } from "~/richText/schema"
import { showFlash } from "~/shared/flash"
import { ChannelEventResource, ChannelStream } from "~/types/channels"
import { chatMessagesQueryKey, chatMessagesQueryOptions } from "./chatMessages"

interface MessageResponse {
  message: ChatMessage
}

const EMPTY_MESSAGES: ChatMessage[] = []

export interface UseChatArgs {
  chatId: string | null
  workspaceId: string | null
  currentUserId: string | null
  currentUserDisplayName: string | null
  initialLastReadAt?: string | null
  initialUnreadCount?: number
  initialDraft?: string
  mailboxEntryId?: string | null
  markReadOnOpen?: boolean
  enableTyping?: boolean
}

export function useChat({
  chatId,
  workspaceId,
  currentUserId,
  currentUserDisplayName,
  initialLastReadAt = null,
  initialUnreadCount = 0,
  initialDraft = "",
  mailboxEntryId = null,
  markReadOnOpen = false,
  enableTyping = false,
}: UseChatArgs) {
  const queryClient = useQueryClient()
  // Stable identity across renders (only changes with chatId): this is fed to React
  // dep arrays below, where Object.is compares by reference. A fresh array literal
  // per render would re-run the re-arm effect every render — its cleanup aborts the
  // in-flight catch-up — and recreate every cache-writing callback.
  const queryKey = useMemo(() => chatMessagesQueryKey(chatId ?? ""), [chatId])

  // The windowed message list lives in the Query cache keyed by chatId, shared by
  // the show page and the panel. The cache value is the MessageListResponse-shaped
  // window: `messages` plus the *older* (backward) cursor. The forward-window
  // state (atTail, hasNewer, the newer cursor) has no home in that envelope and
  // stays local below, since it's only meaningful transiently after a jump.
  const messagesQuery = useQuery(chatMessagesQueryOptions(chatId))
  const messages = messagesQuery.data?.messages ?? EMPTY_MESSAGES
  const loading = messagesQuery.isLoading
  const hasMore = messagesQuery.data?.has_more ?? false

  // Array-updater → envelope patch, so the shared message hooks (subscription,
  // catch-up, reaction toggle) keep their setMessages contract while writing the
  // Query cache. Only `messages` changes here; the cursors ride along untouched.
  const setMessages = useCallback<React.Dispatch<React.SetStateAction<ChatMessage[]>>>(
    update => {
      queryClient.setQueryData<MessageListResponse>(queryKey, prev => {
        const prevMessages = prev?.messages ?? []
        const nextMessages = typeof update === "function" ? update(prevMessages) : update
        return prev
          ? { ...prev, messages: nextMessages }
          : { messages: nextMessages, has_more: false, next_cursor: null }
      })
    },
    [queryClient, queryKey]
  )

  const [loadingMore, setLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false)
  // Forward (newer) pagination, the mirror of loadMore: a cursor + hasNewer +
  // re-entrancy gate. Null cursor means the first newer page should be seeded
  // from the last loaded message id (`after=`); subsequent pages use the
  // returned next_cursor.
  const [loadingNewer, setLoadingNewer] = useState(false)
  const loadingNewerRef = useRef(false)
  const [hasNewer, setHasNewer] = useState(false)
  const nextNewerCursorRef = useRef<string | null>(null)
  const [sending, setSending] = useState(false)
  const sendingRef = useRef(false)
  const [sendError, setSendError] = useState(false)
  const [claimId, setClaimId] = useState(() => crypto.randomUUID())
  const [replyTo, setReplyTo] = useState<ReplyPreview | null>(null)
  const replyToRef = useRef<ReplyPreview | null>(null)
  replyToRef.current = replyTo
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [draftContent, setDraftContentRaw] = useState(initialDraft)
  const [typingUsers, setTypingUsers] = useState<User[]>([])
  const [lastReadAt, setLastReadAt] = useState<string | null>(initialLastReadAt)
  const [unreadMessageCount, setUnreadMessageCount] = useState(initialUnreadCount)

  // True when the loaded list's newest message IS the live tail. The natural
  // signal the whole window model turns on: a real-time NEW_MESSAGE may only be
  // appended (and a reconnect may only splice the latest page) while at the tail
  // — otherwise it would create a gap above a historical window. Seeded true (a
  // fresh chat loads the tail) and flipped false by a jump into a window that
  // isn't caught up; forward pagination (loadNewer) flips it back true on
  // reaching the tail. Callbacks read atTailRef for the live value.
  const [atTail, setAtTail] = useState(true)
  const atTailRef = useRef(true)
  atTailRef.current = atTail

  // Keep mark-read state in sync with caller-supplied initial values (e.g.
  // ChatShow's metadata fetch resolves after mount).
  useEffect(() => {
    setLastReadAt(initialLastReadAt)
  }, [initialLastReadAt])
  useEffect(() => {
    setUnreadMessageCount(initialUnreadCount)
  }, [initialUnreadCount])

  const { composePreview, dismissComposePreview, dismissed: previewDismissed } = useLinkPreviewUnfurl(draftContent)

  // Chat marks read on open, always flushes on unmount, and re-arms per chatId
  // so switching chats in the panel flushes the old one and marks the new one.
  const { notifyIncoming: notifyIncomingMessage } = useMailboxEntryReadTracking({
    mailboxEntryId,
    currentUserId,
    enabled: markReadOnOpen && !!chatId && !!currentUserId,
    markReadOnMount: true,
    resetKey: chatId,
  })

  const { onType, stopTyping } = useTypingBroadcast({
    stream: ChannelStream.CHAT,
    params: chatId && workspaceId ? { chat_id: chatId, workspace_id: workspaceId } : null,
    enabled: enableTyping,
  })

  const setDraftContent = useCallback(
    (content: string) => {
      setDraftContentRaw(content)
      setSendError(false)
      if (!isBlankMarkdown(content)) {
        onType()
      } else {
        stopTyping()
      }
    },
    [onType, stopTyping]
  )

  // Reset the forward window when chatId clears or switches. The messages list,
  // hasMore, and the older cursor now live in the per-chatId Query cache, so they
  // switch automatically with the key (warm cache shows instantly, cold refetches)
  // — only the transient forward-window state has to be reset by hand. Re-arm the
  // catch-up gate too: switching chats (SPA nav or the panel) reuses this mounted
  // hook, so the warm-cache catch-up below must fire per chatId, not once ever.
  const didMountCatchUpRef = useRef(false)
  useEffect(() => {
    setAtTail(true)
    setHasNewer(false)
    nextNewerCursorRef.current = null
    didMountCatchUpRef.current = false
  }, [chatId])

  const { catchUp } = useCatchUpMessages({
    chatId,
    workspaceId,
    setMessages,
    isAtTail: () => atTailRef.current,
  })

  // Subscription re-arm catch-up: a warm cache when this chatId becomes active
  // means a prior mount fetched messages while this hook's subscription missed
  // pushes (SPA navigation to another chat and back, or the panel switching chats
  // without remounting); staleTime:Infinity won't refetch and no "reconnected"
  // fires (the socket never dropped). Splice the latest page in (atTail-gated). A
  // cold chatId has no cached data yet, so it's skipped and the initial useQuery
  // fetch covers it. The reset effect above re-arms the gate on each chatId switch.
  useEffect(() => {
    if (!chatId || didMountCatchUpRef.current) return
    didMountCatchUpRef.current = true
    if (queryClient.getQueryData(queryKey) === undefined) return
    const controller = new AbortController()
    void catchUp(controller.signal).catch(() => {})
    return () => controller.abort()
  }, [chatId, queryClient, queryKey, catchUp])

  useChatMessageSubscription(chatId, workspaceId, setMessages, {
    onNewMessage: msg => notifyIncomingMessage(msg.user.id),
    isAtTail: () => atTailRef.current,
  })

  useChatChannel(chatId, workspaceId, ChannelEventResource.CHAT_TYPING, (_action, data) => {
    if (!enableTyping) return
    const users = (data.users as User[]) || []
    setTypingUsers(users.filter(u => u.id !== currentUserId))
  })

  const loadMore = useCallback(async () => {
    if (!chatId) return
    const cursor = queryClient.getQueryData<MessageListResponse>(queryKey)?.next_cursor
    if (!cursor || loadingMoreRef.current) return

    loadingMoreRef.current = true
    setLoadingMore(true)
    try {
      const data = await apiFetch<MessageListResponse>(
        `/api/chats/${chatId}/messages?cursor=${encodeURIComponent(cursor)}`
      )
      queryClient.setQueryData<MessageListResponse>(queryKey, prev => ({
        messages: mergeDedup(prev?.messages ?? [], data.messages, "older"),
        has_more: data.has_more,
        next_cursor: data.next_cursor,
      }))
    } catch {
      showFlash("Couldn't load older messages.")
    } finally {
      loadingMoreRef.current = false
      setLoadingMore(false)
    }
  }, [chatId, queryClient, queryKey])

  // Forward pagination, the mirror of loadMore: append the next page of NEWER
  // messages to close the gap between a historical window and the live tail.
  // The first page is seeded from the last loaded message id (`after=`), then
  // subsequent pages follow the returned cursor. Reaching the tail (has_more
  // false) flips atTail back true, so live append/merge resume on their own.
  // Only `.messages` changes — the older cursor/has_more (loadMore's direction)
  // are left untouched.
  const loadNewer = useCallback(async () => {
    if (!chatId) return
    if (loadingNewerRef.current) return
    loadingNewerRef.current = true
    setLoadingNewer(true)
    try {
      const cursor = nextNewerCursorRef.current
      let url: string
      if (cursor) {
        url = `/api/chats/${chatId}/messages?direction=newer&cursor=${encodeURIComponent(cursor)}`
      } else {
        const current = queryClient.getQueryData<MessageListResponse>(queryKey)?.messages ?? []
        const lastId = current[current.length - 1]?.id
        if (!lastId) return
        url = `/api/chats/${chatId}/messages?direction=newer&after=${encodeURIComponent(lastId)}`
      }
      const data = await apiFetch<MessageListResponse>(url)
      queryClient.setQueryData<MessageListResponse>(queryKey, prev =>
        prev
          ? { ...prev, messages: mergeDedup(prev.messages, data.messages, "newer") }
          : { messages: data.messages, has_more: false, next_cursor: null }
      )
      nextNewerCursorRef.current = data.next_cursor
      setHasNewer(data.has_more)
      // No more newer pages → the loaded bottom is the live tail again.
      if (!data.has_more) setAtTail(true)
    } catch {
      showFlash("Couldn't load newer messages.")
    } finally {
      loadingNewerRef.current = false
      setLoadingNewer(false)
    }
  }, [chatId, queryClient, queryKey])

  // Load a bounded window centered on `messageId` and REPLACE the list with it,
  // so jumping to a quoted message works regardless of how far back it is. The
  // window's older cursor feeds the existing loadMore unchanged; when the window
  // isn't caught up (at_tail false), forward pagination (loadNewer) closes the
  // gap to the tail. Returns the response, or null on 404/error so
  // useScrollToReply can show the "couldn't find" flash without a throw.
  const jumpToMessage = useCallback(
    async (messageId: string): Promise<MessageWindowResponse | null> => {
      if (!chatId) return null
      try {
        const data = await apiFetch<MessageWindowResponse>(`/api/chats/${chatId}/messages/around/${messageId}`)
        queryClient.setQueryData<MessageListResponse>(queryKey, {
          messages: data.messages,
          has_more: data.has_more,
          next_cursor: data.next_cursor,
        })
        setAtTail(data.at_tail)
        setHasNewer(!data.at_tail)
        // First forward page seeds from the window's last id (`after=`).
        nextNewerCursorRef.current = null
        return data
      } catch {
        return null
      }
    },
    [chatId, queryClient, queryKey]
  )

  // Fast-skip back to the live tail: refetch the initial (no-cursor) page, which
  // replaces the cache window with the newest page, then reset the forward
  // cursors and atTail. The alternative — paginating forward page by page — could
  // be arbitrarily many requests from a deep window.
  const jumpToLatest = useCallback(async () => {
    await queryClient.refetchQueries({ queryKey })
    setAtTail(true)
    setHasNewer(false)
    nextNewerCursorRef.current = null
  }, [queryClient, queryKey])

  const sendMutation = useMutation({
    mutationFn: (vars: { content: string; attachmentClaimId?: string; replyToId?: string }) => {
      const body: Record<string, unknown> = {
        content: vars.content.trimEnd(),
        skip_link_preview: previewDismissed,
      }
      if (vars.attachmentClaimId) body.attachment_claim_id = vars.attachmentClaimId
      if (vars.replyToId) body.reply_to_id = vars.replyToId
      return apiFetch<MessageResponse>(`/api/chats/${chatId}/messages`, { method: "POST", body: JSON.stringify(body) })
    },
    onSuccess: (data, vars) => {
      setMessages(prev => insertInOrder(prev, data.message).messages)
      setDraftContentRaw("")
      setClaimId(crypto.randomUUID())
      setReplyTo(prev => (prev?.id === vars.replyToId ? null : prev))
      stopTyping()
    },
  })

  const sendMessage = useCallback(
    async (content: string, attachmentClaimId?: string) => {
      if (!chatId) return
      if (isBlankMarkdown(content) || sendingRef.current) return

      sendingRef.current = true
      setSending(true)
      setSendError(false)
      try {
        await sendMutation.mutateAsync({ content, attachmentClaimId, replyToId: replyToRef.current?.id })
      } catch {
        setSendError(true)
      } finally {
        sendingRef.current = false
        setSending(false)
      }
    },
    [chatId, sendMutation]
  )

  const editMutation = useMutation({
    mutationFn: (vars: {
      messageId: string
      content: string
      attachmentClaimId: string | null
      retainedAttachmentIds: string[]
    }) =>
      apiFetch<MessageResponse>(`/api/chats/${chatId}/messages/${vars.messageId}`, {
        method: "PATCH",
        body: JSON.stringify({
          content: vars.content,
          attachment_claim_id: vars.attachmentClaimId,
          retained_attachment_ids: vars.retainedAttachmentIds,
        }),
      }),
    onSuccess: data => {
      setMessages(prev => prev.map(m => (m.id === data.message.id ? data.message : m)))
      setEditingMessageId(null)
    },
  })

  const editMessage = useCallback(
    async (messageId: string, content: string, attachmentClaimId: string | null, retainedAttachmentIds: string[]) => {
      if (!chatId) return
      try {
        await editMutation.mutateAsync({ messageId, content, attachmentClaimId, retainedAttachmentIds })
      } catch (err) {
        showFlash("Couldn't save edit.")
        throw err
      }
    },
    [chatId, editMutation]
  )

  const deleteMutation = useMutation({
    mutationFn: (messageId: string) => apiFetch(`/api/chats/${chatId}/messages/${messageId}`, { method: "DELETE" }),
    onSuccess: (_data, messageId) => {
      setMessages(prev => prev.filter(m => m.id !== messageId))
    },
  })

  const deleteMessage = useCallback(
    async (messageId: string) => {
      if (!chatId) return
      if (!(await confirm({ message: "Are you sure you want to delete this message?" }))) return
      try {
        await deleteMutation.mutateAsync(messageId)
      } catch {
        showFlash("Couldn't delete message.")
      }
    },
    [chatId, deleteMutation]
  )

  const toggleReaction = useReactionToggle<ChatMessage, MessageResponse>({
    currentUser: currentUserId ? { id: currentUserId, display_name: currentUserDisplayName ?? "" } : null,
    setItems: setMessages,
    buildUrl: (messageId, reactionType) =>
      `/api/chats/${chatId}/messages/${messageId}/reactions?reaction_type=${encodeURIComponent(reactionType)}`,
    parseReactions: data => data.message.reactions,
  })

  const cancelEdit = useCallback(() => setEditingMessageId(null), [])

  return {
    messages,
    setMessages,
    loading,
    loadingMore,
    hasMore,
    sending,
    sendError,
    claimId,
    replyTo,
    setReplyTo,
    editingMessageId,
    setEditingMessageId,
    cancelEdit,
    draftContent,
    setDraftContent,
    composePreview,
    dismissComposePreview,
    lastReadAt,
    setLastReadAt,
    unreadMessageCount,
    setUnreadMessageCount,
    typingUsers,
    loadMore,
    loadNewer,
    loadingNewer,
    hasNewer,
    jumpToMessage,
    jumpToLatest,
    atTail,
    sendMessage,
    editMessage,
    deleteMessage,
    toggleReaction,
  }
}
