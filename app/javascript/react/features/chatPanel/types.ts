import type { ChatCollaborator, ChatType } from "~/react/shared/types"

export interface ChatPanelTarget {
  id: string
  displayName: string
  picture: string | null
}

export interface ChatPanelDisplay {
  title: string
  type: ChatType
  collaborators: ChatCollaborator[]
}

export interface ChatPanelState {
  chatId: string | null
  workspaceId: string | null
  uploadUrl: string | null
  supportsMentions: boolean
  display: ChatPanelDisplay
  minimized: boolean
  draftContent: string
  // True when display fields are placeholders or stale (opened by chat-id, or
  // synthesized from a recipient profile before the server confirms the chat).
  // The metadata-fetch effect clears this once /api/chats/{id} reconciles.
  incomplete: boolean
  // Set when the metadata-fetch effect's GET fails. Gates the effect so it
  // doesn't loop, and prompts the panel to render an inline retry CTA.
  loadFailed: boolean
}

export type OpenChatPanelEvent =
  | {
      kind: "recipient"
      recipientId: string
      recipientName: string
      recipientPicture: string | null
    }
  | {
      kind: "chat"
      chatId: string
      title?: string
      picture?: string | null
    }
