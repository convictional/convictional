import { useCallback, useEffect, useRef } from "react"

import { getChannelsClient } from "~/channels/client"
import { ChannelMessageType, type ChannelParams, type ChannelStream } from "~/types/channels"

// How long a single burst of typing stays "live" before we auto-emit a stop.
// The receiver clears its indicator on the same window if the channel goes
// silent, so the two are intentionally the same value.
const TYPING_TIMEOUT_MS = 3000

interface UseTypingBroadcastOptions {
  stream: ChannelStream
  // Channel params identifying the topic (e.g. { chat_id, workspace_id } or
  // { email_thread_id }). null disables broadcasting until the id resolves.
  params: ChannelParams | null
  // Surfaces that can turn typing off entirely (e.g. chat's enableTyping flag).
  enabled?: boolean
}

interface UseTypingBroadcastResult {
  // Call on each keystroke of a non-empty draft. Emits is_typing:true once per
  // burst and (re)arms the auto-stop timer.
  onType: () => void
  // Call when the draft empties, on send, or to force-stop. Emits is_typing:false
  // only if we were signaling typing.
  stopTyping: () => void
}

// Broadcasts debounced TYPING frames over a channel topic: is_typing:true on the
// first keystroke of a burst, is_typing:false after TYPING_TIMEOUT_MS of silence,
// on an explicit stop, or on unmount. Parameterized by stream + topic params so
// any composer can drive its typing indicator without reimplementing the debounce.
export function useTypingBroadcast({
  stream,
  params,
  enabled = true,
}: UseTypingBroadcastOptions): UseTypingBroadcastResult {
  const isTypingRef = useRef(false)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Read the latest config through a ref so onType/stopTyping keep a stable
  // identity — they feed the editor's onChange on every keystroke.
  const configRef = useRef({ stream, params, enabled })
  configRef.current = { stream, params, enabled }

  const stopTyping = useCallback(() => {
    const { stream, params, enabled } = configRef.current
    if (!enabled || !params) return
    if (!isTypingRef.current) return
    const client = getChannelsClient()
    if (!client) return
    isTypingRef.current = false
    client.broadcastTo(stream, params, { type: ChannelMessageType.TYPING, is_typing: false })
    if (typingTimerRef.current) {
      clearTimeout(typingTimerRef.current)
      typingTimerRef.current = null
    }
  }, [])

  const onType = useCallback(() => {
    const { stream, params, enabled } = configRef.current
    if (!enabled || !params) return
    const client = getChannelsClient()
    if (!client) return

    if (!isTypingRef.current) {
      isTypingRef.current = true
      client.broadcastTo(stream, params, { type: ChannelMessageType.TYPING, is_typing: true })
    }

    if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
    typingTimerRef.current = setTimeout(stopTyping, TYPING_TIMEOUT_MS)
  }, [stopTyping])

  useEffect(() => {
    return () => stopTyping()
  }, [stopTyping])

  return { onType, stopTyping }
}
