// Visual + copy metadata per resource type. Keyed by the backend's record_type.
// Lives in shared/ so the notifications settings island and per-resource bells
// (chat, posts, etc.) can stay in sync without crossing island boundaries.
export interface SourceMeta {
  label: string
  icon: string // Material Symbols name
  // Singular noun for an individual subscription of this resource (e.g. "post",
  // "thread"). Plural is `unit + "s"`. Used in cascade copy where the label
  // ("Chat", "Shared email") doesn't pluralize cleanly.
  unit: string
  // Label and description for the "broadcasts" middle option. Present only on
  // resource types that distinguish posts addressed to the whole organization
  // from narrower-scope posts (today: Post). When set, SourceRow renders three
  // radios instead of two.
  broadcastsLabel?: string
  broadcastsDescription?: string
  allDescription: string
  relevantDescription: string
  // Optional clarifier shown under the source label — for delivery quirks
  // (email always arrives) or baseline guarantees (your groups reach you).
  note?: string
}

export type SourceKey = "Post" | "Chat" | "EmailThread" | "Goal" | "Meeting" | "Document"

export const SOURCE_META: Record<SourceKey, SourceMeta> = {
  Post: {
    label: "Posts",
    icon: "forum",
    unit: "post",
    broadcastsLabel: "Everyone and my groups",
    broadcastsDescription: "Posts addressed to the whole organization",
    allDescription: "Every post in your organization, even from groups you haven't joined",
    relevantDescription: "Your groups, @mentions, and replies on your posts",
  },
  Chat: {
    label: "Chat",
    icon: "chat",
    unit: "chat",
    allDescription: "Every message",
    relevantDescription: "@mentions",
  },
  EmailThread: {
    label: "Shared email",
    icon: "mail",
    unit: "thread",
    allDescription: "Every reply and comment",
    relevantDescription: "@mentions",
    note: "Email always arrives in your inbox.",
  },
  Goal: {
    label: "Goals",
    icon: "target",
    unit: "goal",
    allDescription: "Every lifecycle change, comment, and update",
    relevantDescription: "@mentions, comments on yours, update requests",
  },
  Meeting: {
    label: "Meetings",
    icon: "calendar_month",
    unit: "meeting",
    allDescription: "Every update, agenda change, and transcript",
    relevantDescription: "@mentions, meetings you've been added to, comments on yours",
  },
  Document: {
    label: "Documents",
    icon: "description",
    unit: "document",
    allDescription: "Every comment",
    relevantDescription: "@mentions, comments on yours",
  },
}

export function sourceMetaFor(key: string): SourceMeta | undefined {
  return SOURCE_META[key as SourceKey]
}
