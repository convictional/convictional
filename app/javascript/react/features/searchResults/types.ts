export type ContentTypeFilter = "meeting" | "post" | "goal" | "document" | "email_thread" | "chat" | "decision"

export const CONTENT_TYPE_FILTERS: { value: ContentTypeFilter | null; label: string }[] = [
  { value: null, label: "Everything" },
  { value: "meeting", label: "Meetings" },
  { value: "post", label: "Posts" },
  { value: "goal", label: "Goals" },
  { value: "document", label: "Docs" },
  { value: "email_thread", label: "Emails" },
  { value: "chat", label: "Chats" },
  { value: "decision", label: "Decisions" },
]
