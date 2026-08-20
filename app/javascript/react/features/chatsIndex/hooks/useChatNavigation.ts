import { useLocation, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch, ApiError } from "~/react/shared/apiFetch"
import type { ChatCreatedResponse } from "../types"

export function useChatNavigation() {
  const [navigating, setNavigating] = useState(false)
  const [navigatingId, setNavigatingId] = useState<string | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const navigatingRef = useRef(false)
  const mountedRef = useRef(true)
  const navigate = useNavigate()
  // The current index URL (with any group filter) — stamped as the chat's back
  // target so its header "back" returns here.
  const returnTo = useLocation({ select: location => location.href })

  useEffect(() => {
    // Reset on (re)mount so StrictMode's mount→unmount→remount doesn't leave the
    // ref stuck false — otherwise createAndNavigate's post-await navigate() is
    // skipped forever and the compose/contact spinner never resolves.
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const createAndNavigate = useCallback(
    async (body: Record<string, unknown>, itemId?: string) => {
      if (navigatingRef.current) return
      navigatingRef.current = true
      setNavigating(true)
      if (itemId) setNavigatingId(itemId)
      setCreateError(null)

      try {
        const data = await apiFetch<ChatCreatedResponse>("/api/chats", {
          method: "POST",
          body: JSON.stringify(body),
        })
        if (mountedRef.current)
          void navigate({ to: "/chats/$chatId", params: { chatId: data.chat_id }, search: { return_to: returnTo } })
      } catch (e) {
        if (!mountedRef.current) return
        navigatingRef.current = false
        setNavigating(false)
        if (itemId) setNavigatingId(null)
        if (e instanceof ApiError) {
          setCreateError(e.message)
        } else {
          setCreateError("Something went wrong. Please try again.")
        }
      }
    },
    [navigate, returnTo]
  )

  const selectChat = useCallback(
    (chatId: string) => {
      if (navigatingRef.current) return
      navigatingRef.current = true
      setNavigating(true)
      setNavigatingId(chatId)
      void navigate({ to: "/chats/$chatId", params: { chatId }, search: { return_to: returnTo } })
    },
    [navigate, returnTo]
  )

  return {
    navigating,
    navigatingId,
    createError,
    setCreateError,
    createAndNavigate,
    selectChat,
  }
}
