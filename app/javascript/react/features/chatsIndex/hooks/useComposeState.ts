import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { PaginatedResponse } from "~/react/shared/types"
import type { ChatListItem, Contact, GroupMatch, SelectedRecipient } from "../types"

interface LookupResult {
  matches: ChatListItem[]
  matchGroup: GroupMatch | null
}

interface ChatLookupResponse extends PaginatedResponse {
  matches: ChatListItem[]
  match_group: GroupMatch | null
}

export function useComposeState(currentUserId: string | null, chats: ChatListItem[], contacts: Contact[]) {
  const [composeMode, setComposeMode] = useState(false)
  const [selectedRecipients, setSelectedRecipients] = useState<SelectedRecipient[]>([])
  const [lookupResult, setLookupResult] = useState<LookupResult | null>(null)
  const [lookupPending, setLookupPending] = useState(false)
  const [lookupError, setLookupError] = useState(false)
  const lookupAbortRef = useRef<AbortController | null>(null)

  const composing = composeMode

  // Derive public lookup values — when not composing, always empty/null/false
  const existingMatches = composing ? (lookupResult?.matches ?? []) : []
  const existingMatchGroup = composing ? (lookupResult?.matchGroup ?? null) : null
  const lookingUp = composing && lookupPending

  // An exact-membership chat exists when some match has collaborator_count equal to the recipient count + self
  const exactMatchExists = existingMatches.some(chat => chat.collaborator_count === selectedRecipients.length + 1)

  const toggleRecipient = useCallback((recipient: SelectedRecipient) => {
    setComposeMode(true)
    setSelectedRecipients(prev => {
      const exists = prev.some(r => r.id === recipient.id)
      return exists ? prev.filter(r => r.id !== recipient.id) : [...prev, recipient]
    })
    setLookupResult(null)
    setLookupPending(true)
    setLookupError(false)
  }, [])

  const removeRecipient = useCallback((id: string) => {
    setSelectedRecipients(prev => {
      const next = prev.filter(r => r.id !== id)
      if (next.length === 0) {
        setComposeMode(false)
        setLookupError(false)
      }
      setLookupResult(null)
      setLookupPending(next.length > 0)
      return next
    })
  }, [])

  const clearRecipients = useCallback(() => {
    setComposeMode(false)
    setSelectedRecipients([])
    setLookupResult(null)
    setLookupPending(false)
    setLookupError(false)
  }, [])

  const toggleComposeMode = useCallback(() => {
    setComposeMode(prev => !prev)
    setSelectedRecipients([])
    setLookupResult(null)
    setLookupPending(false)
    setLookupError(false)
  }, [])

  // All org users (union of DM chat users + contacts) for compose mode
  const allUsers = useMemo(() => {
    const users: SelectedRecipient[] = []
    const seen = new Set<string>()
    if (currentUserId) seen.add(currentUserId)

    for (const chat of chats) {
      if (chat.type === "dm" && chat.user && !seen.has(chat.user.id)) {
        seen.add(chat.user.id)
        users.push({ id: chat.user.id, name: chat.user.display_name, picture: chat.user.picture })
      }
    }

    for (const contact of contacts) {
      if (contact.type === "dm" && !seen.has(contact.id)) {
        seen.add(contact.id)
        users.push({ id: contact.id, name: contact.name, picture: contact.picture })
      }
    }

    return users.sort((a, b) => a.name.localeCompare(b.name))
  }, [chats, contacts, currentUserId])

  // Debounced lookup when 1+ recipients selected (includes currentUserId so 1 chip = 2-ID lookup)
  useEffect(() => {
    if (selectedRecipients.length < 1 || !currentUserId) return

    const timer = setTimeout(() => {
      lookupAbortRef.current?.abort()
      const controller = new AbortController()
      lookupAbortRef.current = controller

      const userIds = [currentUserId, ...selectedRecipients.map(r => r.id)]
      const params = userIds.map(id => `user_ids=${encodeURIComponent(id)}`).join("&")

      apiFetch<ChatLookupResponse>(`/api/chats/lookup?${params}`, {
        signal: controller.signal,
      })
        .then(data => {
          if (!controller.signal.aborted) {
            setLookupResult({ matches: data.matches, matchGroup: data.match_group })
            setLookupPending(false)
          }
        })
        .catch(() => {
          if (controller.signal.aborted) return
          setLookupResult(null)
          setLookupPending(false)
          setLookupError(true)
        })
    }, 250)

    return () => {
      clearTimeout(timer)
      lookupAbortRef.current?.abort()
    }
  }, [selectedRecipients, currentUserId])

  return {
    selectedRecipients,
    composing,
    existingMatches,
    existingMatchGroup,
    exactMatchExists,
    lookingUp,
    allUsers,
    lookupError,
    toggleRecipient,
    removeRecipient,
    clearRecipients,
    toggleComposeMode,
  }
}
