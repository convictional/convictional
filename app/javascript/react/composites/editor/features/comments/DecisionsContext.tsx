import { createContext, useContext } from "react"

import type { Decision } from "~/react/shared/types"

interface DecisionsContextValue {
  // comment_gid -> decision, for the per-comment inline marker.
  decisionsByGid: Map<string, Decision>
  // Single-click toggle keyed by the comment's global_id. Undefined when the
  // host editor doesn't support decisions (e.g. post drafts, whose comments
  // aren't anchorable) — the marker is hidden in that case. The comment system
  // is shared across editors, so decisions opt in via this provider rather than
  // being threaded as props through every layer that doesn't use them.
  onToggleDecision?: (commentGid: string) => void
}

const DecisionsContext = createContext<DecisionsContextValue>({ decisionsByGid: new Map() })

export const DecisionsProvider = DecisionsContext.Provider
export const useDecisionsContext = () => useContext(DecisionsContext)
