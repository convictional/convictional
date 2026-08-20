import type { User } from "~/react/shared/types"

// Opens the desktop chat panel as a DM with the given user by dispatching the
// `open-chat-panel` event the chat-panel island listens for
// (features/chatPanel/useChatPanelState). Mobile has no panel — callers there
// post to /chats instead. The `recipient` detail shape lives here so its emitters
// (ProfileCard, the org-users island) stay on one canonical payload.
export function openDirectMessagePanel(user: User): void {
  window.dispatchEvent(
    new CustomEvent("open-chat-panel", {
      detail: {
        kind: "recipient",
        recipientId: user.id,
        recipientName: user.display_name,
        recipientPicture: user.picture,
      },
    })
  )
}
