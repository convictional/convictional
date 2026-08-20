import { useCallback, useRef } from "react"
import type { Dispatch, SetStateAction } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { toggleReactionInMap } from "~/react/shared/reactions"
import type { ReactionUser } from "~/react/shared/types"

interface ReactableItem {
  id: string
  reactions: Record<string, ReactionUser[]>
}

interface UseReactionToggleOptions<T extends ReactableItem, TResponse> {
  // The reacting user, or null before it has loaded. When null we skip the
  // optimistic splice (the reaction can't be attributed) but still POST, so a
  // click during the load window isn't silently dropped.
  currentUser: ReactionUser | null
  setItems: Dispatch<SetStateAction<T[]>>
  buildUrl: (id: string, reactionType: string) => string
  // Pulls the authoritative reactions map out of the toggle response. We merge
  // only the reactions, never the whole record: the response carries a
  // transient auto_now updated_at that would otherwise flip an "(edited)" badge.
  parseReactions: (response: TResponse) => Record<string, ReactionUser[]>
  onError?: () => void
}

// Optimistic reaction toggle for flat, id-keyed lists (chat messages,
// email-thread comments). Splices the reaction in immediately, POSTs, then
// reconciles with the server's reactions. On failure it re-applies the toggle —
// which is its own inverse — to revert our own change against the latest state,
// so concurrent reaction updates from other users aren't clobbered.
export function useReactionToggle<T extends ReactableItem, TResponse>(
  options: UseReactionToggleOptions<T, TResponse>
): (id: string, reactionType: string) => Promise<void> {
  // Read options through a ref so callers can pass fresh closures each render
  // without changing the returned callback's identity (it feeds memoized rows).
  const optionsRef = useRef(options)
  optionsRef.current = options

  return useCallback(async (id: string, reactionType: string) => {
    const { currentUser, setItems, buildUrl, parseReactions, onError } = optionsRef.current

    const applyToggle = () => {
      if (!currentUser) return
      setItems(prev =>
        prev.map(item =>
          item.id === id
            ? { ...item, reactions: toggleReactionInMap(item.reactions, reactionType, currentUser) }
            : item
        )
      )
    }

    applyToggle()
    try {
      const response = await apiFetch<TResponse>(buildUrl(id, reactionType), { method: "POST" })
      const reactions = parseReactions(response)
      setItems(prev => prev.map(item => (item.id === id ? { ...item, reactions } : item)))
    } catch {
      applyToggle()
      onError?.()
    }
  }, [])
}
