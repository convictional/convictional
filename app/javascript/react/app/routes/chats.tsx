import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"

import { shellRoute } from "../shellRoute"

// See notifications.tsx for the route-definition conventions. lazyRouteComponent
// code-splits the page chunk while the route's contracts (validateSearch) stay eager.
const ChatsIndexView = lazyRouteComponent(() => import("~/react/features/chatsIndex/ChatsIndex"), "ChatsIndex")

// `group_id` is the only search param the index carries — the CollaboratorPanel's
// "continue in group" branch navigates here with it. Nothing consumes it today
// (the group filter is local state), so validateSearch just preserves it round-trip
// rather than adding behavior.
export interface ChatsIndexSearch {
  group_id?: string
}

function ChatsPage() {
  useDocumentTitle("Chat")
  return <ChatsIndexView />
}

export const chatsIndexRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/chats",
  validateSearch: (search: Record<string, unknown>): ChatsIndexSearch => ({
    group_id: typeof search.group_id === "string" ? search.group_id : undefined,
  }),
  component: ChatsPage,
})
