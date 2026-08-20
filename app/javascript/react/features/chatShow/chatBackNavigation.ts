import { backNavigation } from "~/react/shared/backNavigation"
import type { BackNavigation } from "~/react/shared/types"

// The chats index is the fallback when the chat wasn't reached from a labeled
// origin. The return_to → label rule itself lives in backNavigation (shared).
export function chatBackNavigation(returnTo: string | undefined): BackNavigation {
  return backNavigation(returnTo, { url: "/chats", label: "Back to chats" })
}
