import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { ChatShowSkeleton } from "~/react/features/chatShow/ChatShowSkeleton"

import { shellRoute } from "../shellRoute"
import { backAndMailboxSearch } from "./mailboxEntryHelpers"

// The chat conversation view. The document title (chat title / group name / "Note
// to self") and the re-sourced "back" affordance are handled in the component,
// since neither is known until the detail fetch resolves (see ChatShow). Channels
// derive from the chat_id route param plus the fetched workspace_id, so the route
// passes no props.
const ChatShowView = lazyRouteComponent(() => import("~/react/features/chatShow/ChatShow"), "ChatShow")

// `return_to` carries the "back" target (the chats index, or the mailbox when the
// chat was opened from an inbox entry), mirroring documentShow. `mailbox_entry_id`
// is present when the chat was opened from an inbox entry; it gates the mailbox
// action bar (see ChatShow) and must be declared here so a client navigation to a
// neighbor entry preserves it (TanStack drops undeclared search params).
export const chatShowRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/chats/$chatId",
  // Chat is full-screen on mobile — suppress the top nav and its bottom offset,
  // matching the Jinja `mobile_nav_hidden` flag the page carried before cutover.
  staticData: { hideMobileNav: true },
  validateSearch: backAndMailboxSearch,
  component: ChatShowView,
  // Paints while the lazy page chunk downloads, so clicking a chat row shows the
  // skeleton instantly — before the page code or its data exist.
  pendingComponent: ChatShowSkeleton,
})
