import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useState } from "react"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useReconnectCatchUp } from "~/react/shared/hooks/useReconnectCatchUp"
import { useReconnectInvalidate } from "~/react/shared/hooks/useReconnectInvalidate"
import { showFlash } from "~/shared/flash"
import { type ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"
import {
  type ChatsListData,
  chatContactsQueryKey,
  chatContactsQueryOptions,
  chatsListQueryKey,
  chatsListQueryOptions,
} from "../queries/chatsList"
import type { ChatListItem, ChatListResponse, ChatType, Contact, GroupFilter, SelectedRecipient } from "../types"
import { useChatNavigation } from "./useChatNavigation"
import { useComposeState } from "./useComposeState"

const EMPTY_CONTACTS: Contact[] = []

export type VisibleItem =
  | { kind: "chat"; chat: ChatListItem }
  | { kind: "contact-divider" }
  | { kind: "contact"; contact: Contact }
  | { kind: "compose-create" }
  | { kind: "compose-match"; chat: ChatListItem }
  | { kind: "compose-match-group" }
  | { kind: "compose-looking-up" }

export function useChatsData(organizationId: string | null, currentUserId: string | null) {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState("")
  const [groupFilter, setGroupFilter] = useState<GroupFilter>("all")
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)

  // --- Data fetching ---
  //
  // The infinite list holds the cursor-paginated chats; a change in loaded pages
  // (loadMore, or a channel push collapsing to one authoritative page) reflows the
  // channel's loaded_pages extraParam. Contacts have no channel, so they ride a
  // plain query. Query + the forwarded signal replace the old AbortController /
  // requestId stale-guarding.
  const listQuery = useInfiniteQuery({
    ...chatsListQueryOptions(),
    // Keep the previous list on screen while a background refetch (reconnect /
    // re-arm) is in flight instead of blanking to a spinner.
    placeholderData: keepPreviousData,
  })
  const contactsQuery = useQuery(chatContactsQueryOptions())

  const chats = useMemo<ChatListItem[]>(
    () => listQuery.data?.pages.flatMap(page => page.chats) ?? [],
    [listQuery.data]
  )
  const contacts = contactsQuery.data?.contacts ?? EMPTY_CONTACTS
  const loading = listQuery.isLoading
  const loadingMore = listQuery.isFetchingNextPage
  const error = listQuery.isError
  const hasMore = listQuery.hasNextPage
  const { fetchNextPage } = listQuery

  const {
    composing,
    selectedRecipients,
    existingMatches,
    existingMatchGroup,
    exactMatchExists,
    lookingUp,
    allUsers,
    lookupError,
    toggleRecipient: baseToggleRecipient,
    removeRecipient: baseRemoveRecipient,
    clearRecipients,
    toggleComposeMode: baseToggleComposeMode,
  } = useComposeState(currentUserId, chats, contacts)

  const { navigating, navigatingId, createError, setCreateError, createAndNavigate, selectChat } = useChatNavigation()

  const loadMore = useCallback(() => {
    if (loadingMore || loading || !hasMore) return
    void fetchNextPage()
  }, [loadingMore, loading, hasMore, fetchNextPage])

  // Walk to the next page while a search is active so the client-side filter in
  // visibleItems sees the full list. Reactive rather than a manual loop: each
  // fetched page flips hasMore/loadingMore, re-running this effect until the list
  // is exhausted. Keyed on searchQuery !== "" (not the text) so per-keystroke
  // filtering doesn't restart pagination.
  const isSearching = searchQuery !== ""
  useEffect(() => {
    if (!isSearching || !hasMore || loadingMore) return
    void fetchNextPage()
  }, [isSearching, hasMore, loadingMore, fetchNextPage])

  // The chats_index channel rebroadcasts the whole loaded_pages-tailored list on
  // any change, so a push replaces every loaded page with one authoritative page.
  const handleChannelMessage = useCallback(
    (_action: ChannelEventAction, data: Record<string, unknown>) => {
      const message = data as unknown as ChatListResponse
      queryClient.setQueryData<ChatsListData>(chatsListQueryKey(), { pages: [message], pageParams: [null] })
    },
    [queryClient]
  )

  useChannel(
    organizationId
      ? {
          stream: ChannelStream.CHATS_INDEX,
          params: { organization_id: organizationId },
          extraParams: { loaded_pages: listQuery.data?.pages.length ?? 0 },
        }
      : null,
    ChannelEventResource.CHATS_INDEX,
    handleChannelMessage
  )

  // Recover broadcasts missed while the socket was down or this island was
  // unmounted (SPA navigation) — channelQueryDefaults disables Query's own
  // refetchOnReconnect. The list also catches up on a warm remount; contacts only
  // needs the reconnect path. See useReconnectCatchUp.
  useReconnectCatchUp(chatsListQueryKey(), "useChatsData")
  useReconnectInvalidate(chatContactsQueryKey(), "useChatsData contacts")

  // --- Visible items ---

  const visibleItems = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    const items: VisibleItem[] = []
    const matchesQuery = (name: string) => !query || name.toLowerCase().includes(query)

    const noteToSelf: Contact | null = currentUserId
      ? { id: currentUserId, type: "self", name: "Note to self", collaborator_count: 0, picture: null }
      : null

    if (composing) {
      if (!query) {
        if (lookingUp) {
          items.push({ kind: "compose-looking-up" })
        } else if (selectedRecipients.length > 0) {
          // Create action at the top so it's the default Enter target
          if (!exactMatchExists && !existingMatchGroup) {
            items.push({ kind: "compose-create" })
          }
          for (const chat of existingMatches) {
            items.push({ kind: "compose-match", chat })
          }
          if (existingMatchGroup) {
            items.push({ kind: "compose-match-group" })
          }
        }
      }

      const selectedIds = new Set(selectedRecipients.map(r => r.id))
      const filteredUsers = allUsers.filter(user => {
        if (selectedIds.has(user.id)) return false
        if (query && !user.name.toLowerCase().includes(query)) return false
        return true
      })

      for (const user of filteredUsers) {
        items.push({
          kind: "contact",
          contact: { id: user.id, type: "dm", name: user.name, collaborator_count: 0, picture: user.picture },
        })
      }

      return items
    }

    // Browse mode: existing behavior
    const filteredChats = chats.filter(chat => {
      if (groupFilter === "groups" && chat.type !== "group") return false
      if (query && !chat.name.toLowerCase().includes(query)) return false
      return true
    })

    for (const chat of filteredChats) {
      items.push({ kind: "chat", chat })
    }

    const filteredContacts = contacts.filter(contact => {
      if (groupFilter === "groups" && contact.type !== "group") return false
      if (query && !contact.name.toLowerCase().includes(query)) return false
      return true
    })

    // Skip when an existing self-chat is already in the list — clicking either goes to the same place.
    const hasSelfChat = chats.some(c => c.type === "self")
    const showNoteToSelf = noteToSelf && !hasSelfChat && groupFilter !== "groups" && matchesQuery(noteToSelf.name)

    if ((filteredContacts.length > 0 || showNoteToSelf) && !query) {
      items.push({ kind: "contact-divider" })
    }

    if (showNoteToSelf) {
      items.push({ kind: "contact", contact: noteToSelf })
    }

    for (const contact of filteredContacts) {
      items.push({ kind: "contact", contact })
    }

    return items
  }, [
    chats,
    contacts,
    searchQuery,
    groupFilter,
    composing,
    allUsers,
    selectedRecipients,
    lookingUp,
    existingMatches,
    existingMatchGroup,
    exactMatchExists,
    currentUserId,
  ])

  const selectableItems = useMemo(() => visibleItems.filter(item => item.kind !== "contact-divider"), [visibleItems])

  // Clamp selectedIndex when list shrinks (e.g. channel push replaces chats with shorter list)
  useEffect(() => {
    setSelectedIndex(prev => Math.min(prev, Math.max(0, selectableItems.length - 1)))
  }, [selectableItems.length])

  // --- Compose actions (wrap sub-hook with cross-cutting side effects) ---

  const toggleRecipient = useCallback(
    (recipient: SelectedRecipient) => {
      baseToggleRecipient(recipient)
      setSearchQuery("")
      setSelectedIndex(0)
      setCreateError(null)
    },
    [baseToggleRecipient, setCreateError]
  )

  const removeRecipient = useCallback(
    (id: string) => {
      baseRemoveRecipient(id)
      setCreateError(null)
    },
    [baseRemoveRecipient, setCreateError]
  )

  const toggleComposeMode = useCallback(() => {
    baseToggleComposeMode()
    setSearchQuery("")
    setSelectedIndex(0)
    setCreateError(null)
  }, [baseToggleComposeMode, setCreateError])

  // --- Navigation actions ---

  const createChat = useCallback(() => {
    if (selectedRecipients.length === 0) return
    createAndNavigate({ recipient_ids: selectedRecipients.map(r => r.id) })
  }, [selectedRecipients, createAndNavigate])

  const selectContact = useCallback(
    (contactId: string, type: ChatType) => {
      const body = type === "group" ? { group_id: contactId } : { recipient_ids: [contactId] }
      createAndNavigate(body, contactId)
    },
    [createAndNavigate]
  )

  // First-run nudge: create a group, join it (the API doesn't auto-join the creator), then open its
  // chat. Throws on failure so the caller can surface it; on success navigation unmounts the caller.
  const createGroupAndOpen = useCallback(
    async (name: string) => {
      const trimmed = name.trim()
      if (!trimmed || !currentUserId) return
      const group = await apiFetch<{ id: string }>("/api/groups", {
        method: "POST",
        body: JSON.stringify({ name: trimmed }),
      })
      await apiFetch(`/api/groups/${group.id}/members`, {
        method: "POST",
        body: JSON.stringify({ user_id: currentUserId }),
      })
      selectContact(group.id, "group")
    },
    [currentUserId, selectContact]
  )

  // First-run nudge: invite a teammate by email (POST /api/organization/users). Handles its own
  // success/error flashes — 422 carries a user-facing reason — then refetches so the invited person
  // shows up and the solo state retires. Rethrows so the caller can reset its submitting state.
  const inviteTeammate = useCallback(
    async (email: string) => {
      try {
        await apiFetch(
          "/api/organization/users",
          { method: "POST", body: JSON.stringify({ email }) },
          { expectedStatuses: [422] }
        )
      } catch (err) {
        const detail = err instanceof ApiError && typeof err.body?.detail === "string" ? err.body.detail : null
        showFlash(detail ?? "Could not send the invite. Please try again.", "error")
        throw err
      }
      showFlash("Invite sent.", "success")
      void queryClient.invalidateQueries({ queryKey: chatsListQueryKey() })
      void queryClient.invalidateQueries({ queryKey: chatContactsQueryKey() })
    },
    [queryClient]
  )

  const setSearchQueryAndResetSelection = useCallback((query: string) => {
    setSearchQuery(query)
    setSelectedIndex(0)
  }, [])

  const setGroupFilterAndResetSelection = useCallback((filter: GroupFilter) => {
    setGroupFilter(filter)
    setSelectedIndex(0)
  }, [])

  // --- Keyboard ---

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedIndex(prev => Math.min(prev + 1, selectableItems.length - 1))
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedIndex(prev => Math.max(prev - 1, 0))
      } else if (e.key === "Enter") {
        e.preventDefault()

        const item = selectableItems[selectedIndex]

        if (!item) return

        if (item.kind === "compose-looking-up") {
          return
        } else if (item.kind === "compose-create") {
          createChat()
        } else if (item.kind === "compose-match") {
          selectChat(item.chat.id)
        } else if (item.kind === "compose-match-group") {
          if (existingMatchGroup) selectContact(existingMatchGroup.id, "group")
        } else if (item.kind === "chat") {
          if (composing && item.chat.type === "dm" && item.chat.user) {
            toggleRecipient({ id: item.chat.user.id, name: item.chat.name, picture: item.chat.picture })
          } else {
            selectChat(item.chat.id)
          }
        } else if (item.kind === "contact") {
          if (composing && item.contact.type !== "group" && item.contact.type !== "self") {
            toggleRecipient({ id: item.contact.id, name: item.contact.name, picture: item.contact.picture })
          } else {
            selectContact(item.contact.id, item.contact.type)
          }
        }
      } else if (e.key === "Backspace" && !searchQuery && selectedRecipients.length > 0) {
        removeRecipient(selectedRecipients[selectedRecipients.length - 1].id)
      } else if (e.key === "Escape") {
        if (composing) {
          clearRecipients()
          setSearchQueryAndResetSelection("")
        } else if (searchQuery) {
          setSearchQueryAndResetSelection("")
        } else {
          ;(e.target as HTMLElement).blur()
        }
      }
    },
    [
      selectableItems,
      selectedIndex,
      selectChat,
      selectContact,
      setSearchQueryAndResetSelection,
      searchQuery,
      selectedRecipients,
      existingMatchGroup,
      composing,
      clearRecipients,
      toggleRecipient,
      removeRecipient,
      createChat,
    ]
  )

  return {
    chats,
    contacts,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    searchQuery,
    setSearchQuery: setSearchQueryAndResetSelection,
    groupFilter,
    setGroupFilter: setGroupFilterAndResetSelection,
    visibleItems,
    selectableItems,
    selectedIndex,
    setSelectedIndex,
    hoveredIndex,
    setHoveredIndex,
    navigating,
    navigatingId,
    createError,
    selectChat,
    selectContact,
    createGroupAndOpen,
    inviteTeammate,
    handleKeyDown,
    // Multi-select
    composing,
    selectedRecipients,
    toggleRecipient,
    removeRecipient,
    existingMatches,
    existingMatchGroup,
    exactMatchExists,
    lookingUp,
    lookupError,
    createChat,
    toggleComposeMode,
  }
}
