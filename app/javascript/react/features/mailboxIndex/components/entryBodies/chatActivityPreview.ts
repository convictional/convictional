import {
  type ActivityContext,
  describeCrossResourceActivity,
} from "~/react/composites/mailboxPreview/crossResourceActivity"
import type { EventAction } from "~/react/shared/types"

type Details = Record<string, unknown>

export interface ChatActivityContext extends ActivityContext {
  resolveUserName?: (id: string) => string | undefined
}

// Map chat's collaborator events to the cross-resource action names so the shared phrasing is used.
const CHAT_TO_CROSS_RESOURCE: Partial<Record<EventAction, EventAction>> = {
  chat_collaborator_added: "added_collaborator",
  chat_collaborator_removed: "removed_collaborator",
}

// Fold chat's id-only collaborator detail into the embedded `collaborator` User record the shared
// helper reads (name from the org-members cache; undefined name → the helper's generic fallback).
function toCrossResourceDetails(details: Details, resolve?: (id: string) => string | undefined): Details {
  const id = details.user_id
  if (typeof id !== "string") return details
  return { collaborator: { id, name: resolve?.(id) } }
}

export function describeChatActivity(
  action: EventAction | null,
  details: Details | null,
  context: ChatActivityContext = {}
): string {
  const data = details ?? {}
  const crossResourceAction = action ? CHAT_TO_CROSS_RESOURCE[action] : undefined
  const shared = describeCrossResourceActivity(
    crossResourceAction ?? action,
    crossResourceAction ? toCrossResourceDetails(data, context.resolveUserName) : data,
    context
  )
  if (shared) return shared

  if (action === "chat_renamed") {
    const title = typeof data.title === "string" ? data.title : null
    if (title) return context.actorName ? `${context.actorName} renamed the chat to ${title}` : `Renamed to ${title}`
    return context.actorName ? `${context.actorName} cleared the chat name` : "Cleared the chat name"
  }
  return "Updated the chat"
}
