import { type InfiniteData, infiniteQueryOptions, queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type { ChatListResponse, ContactListResponse } from "../types"

export type ChatsListData = InfiniteData<ChatListResponse, string | null>

export function chatsListQueryKey() {
  return ["chats"] as const
}

export function chatContactsQueryKey() {
  return ["chatContacts"] as const
}

function chatsUrl(cursor: string | null): string {
  return cursor ? `/api/chats?cursor=${encodeURIComponent(cursor)}` : "/api/chats"
}

// Channel-backed: the chats_index channel is the freshness source (it rebroadcasts
// the whole loaded_pages-tailored list on any change), so no background refetch.
export function chatsListQueryOptions() {
  return infiniteQueryOptions({
    ...channelQueryDefaults,
    queryKey: chatsListQueryKey(),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => apiFetch<ChatListResponse>(chatsUrl(pageParam), { signal }),
    getNextPageParam: lastPage => (lastPage.has_more ? lastPage.next_cursor : undefined),
  })
}

// Contacts have no channel — a plain read that recovers on remount. Fetched
// separately from the list (the old hook coupled them in one Promise.all).
export function chatContactsQueryOptions() {
  return queryOptions({
    queryKey: chatContactsQueryKey(),
    queryFn: ({ signal }) => apiFetch<ContactListResponse>("/api/chats/contacts", { signal }),
  })
}
