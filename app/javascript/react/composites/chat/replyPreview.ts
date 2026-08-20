import { markdownToPlainText } from "~/react/composites/markdown/toPlainText"

// Mirror server-side _reply_preview() in app/routers/api/chats.py — used for
// optimistic UI when composing a reply, before the server response lands.
const REPLY_PREVIEW_MAX_LENGTH = 200

export function replyContentPreview(content: string): string {
  return markdownToPlainText(content, { maxLength: REPLY_PREVIEW_MAX_LENGTH })
}
