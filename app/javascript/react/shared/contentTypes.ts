import type { CSSProperties } from "react"

// Mirrors ICON_MAP in app/helpers/workspaces.py — keep in sync.
export const CONTENT_TYPE_ICONS: Record<string, string> = {
  meeting: "calendar_month",
  post: "feed",
  goal: "target",
  document: "description",
  email_thread: "mail",
  chat: "chat_bubble",
  decision: "alt_route",
  user: "person",
  email_contact: "contact_mail",
  group: "groups",
}

// Singular, user-facing label for one resource of each kind. Distinct from the
// plural main-nav tab labels.
export const CONTENT_TYPE_LABELS: Record<string, string> = {
  meeting: "Meeting",
  post: "Post",
  goal: "Goal",
  document: "Document",
  email_thread: "Email",
  chat: "Chat",
}

// The decision marker's accent (matches --color-decision-content in daisyui.css),
// reused for the decision icon badge and the decision_count indicator on parent cards.
export const DECISION_ACCENT_COLOR = "#4d6847"

// Per-content-type badge styling for icon badges in search results and command palette
export const CONTENT_TYPE_ICON_STYLES: Record<
  string,
  {
    text: string
    bg: string
    color: string
    bgColor: string
    texture: string
    textureSize: string
    badgeClass?: string
    badgeStyle?: CSSProperties
  }
> = {
  meeting: {
    text: "text-[#4a6fa5]",
    bg: "bg-[#eaf0f7]",
    color: "#4a6fa5",
    bgColor: "#4a6fa50a",
    texture: `radial-gradient(circle, #4a6fa530 0.4px, transparent 0.4px)`,
    textureSize: "4px 4px",
  },
  post: {
    text: "text-[#7a9e6b]",
    bg: "bg-[#f0f4ed]",
    color: "#7a9e6b",
    bgColor: "#7a9e6b0a",
    texture: `repeating-linear-gradient(0deg, #7a9e6b20 0px, #7a9e6b20 1px, transparent 1px, transparent 4px)`,
    textureSize: "4px 4px",
  },
  goal: {
    text: "text-[#4a6fa5]",
    bg: "bg-[#eaf0f7]",
    color: "#4a6fa5",
    bgColor: "#4a6fa50a",
    badgeClass: "rounded-full",
    texture: `radial-gradient(circle at center, #4a6fa566 0%, transparent 5%, transparent 10%, #4a6fa555 12%, transparent 17%, transparent 22%, #4a6fa54a 24%, transparent 29%, transparent 34%, #4a6fa540 36%, transparent 41%, transparent 46%, #4a6fa538 48%, transparent 53%, transparent 58%, #4a6fa530 60%, transparent 65%, transparent 70%, #4a6fa528 72%, transparent 77%, transparent 82%, #4a6fa522 84%, transparent 89%)`,
    textureSize: "100% 100%",
  },
  document: {
    text: "text-[#5b82b8]",
    bg: "bg-[#ecf1f8]",
    color: "#5b82b8",
    bgColor: "#5b82b80a",
    texture: `linear-gradient(45deg, #5b82b818 25%, transparent 25%, transparent 50%, #5b82b818 50%, #5b82b818 75%, transparent 75%)`,
    textureSize: "5px 5px",
  },
  email_thread: {
    text: "text-[#5d8a6a]",
    bg: "bg-[#edf3ef]",
    color: "#5d8a6a",
    bgColor: "#5d8a6a0a",
    texture: `repeating-linear-gradient(90deg, #5d8a6a20 0px, #5d8a6a20 1px, transparent 1px, transparent 4px), repeating-linear-gradient(0deg, #5d8a6a20 0px, #5d8a6a20 1px, transparent 1px, transparent 4px)`,
    textureSize: "4px 4px",
  },
  chat: {
    text: "text-[#4a6fa5]",
    bg: "bg-[#eaf0f7]",
    color: "#4a6fa5",
    bgColor: "#4a6fa50a",
    texture: `radial-gradient(circle, #4a6fa528 0.6px, transparent 0.6px), radial-gradient(circle, #4a6fa515 0.6px, transparent 0.6px)`,
    textureSize: "6px 6px",
  },
  decision: {
    text: "text-[#4d6847]",
    bg: "bg-[#e6ede3]",
    color: DECISION_ACCENT_COLOR,
    bgColor: "#4d68470a",
    texture: `repeating-linear-gradient(135deg, #4d684720 0px, #4d684720 1px, transparent 1px, transparent 5px)`,
    textureSize: "5px 5px",
  },
  group: {
    text: "text-[#4a6fa5]",
    bg: "bg-[#eaf0f7]",
    color: "#4a6fa5",
    bgColor: "#4a6fa50a",
    // Paired dots read as members clustered into a group, distinct from chat's even dot field.
    texture: `radial-gradient(circle at 32% 50%, #4a6fa526 1px, transparent 1.4px), radial-gradient(circle at 68% 50%, #4a6fa526 1px, transparent 1.4px)`,
    textureSize: "9px 9px",
  },
}
