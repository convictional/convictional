import type { PaginatedResponse, ChatCollaborator, ChatMessage, ChatType, User } from "~/react/shared/types"

export type { ChatCollaborator, ChatCreatedResponse, ChatMessage, ChatType, GroupMatch } from "~/react/shared/types"

export interface ChatListItem {
  id: string
  type: ChatType
  name: string
  collaborator_count: number
  collaborators: ChatCollaborator[] | null
  latest_message: ChatMessage | null
  user: User | null
  picture: string | null
  is_unread: boolean
  is_archived: boolean
  snoozed_until: string | null
}

export interface ChatListResponse extends PaginatedResponse {
  chats: ChatListItem[]
}

export interface Contact {
  id: string
  type: ChatType
  name: string
  collaborator_count: number
  picture: string | null
}

export interface ContactListResponse extends PaginatedResponse {
  contacts: Contact[]
}

export interface SelectedRecipient {
  id: string
  name: string
  picture: string | null
}

export type GroupFilter = "all" | "groups"
