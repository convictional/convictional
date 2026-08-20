import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { ChannelEventResource, ChannelStream } from "~/types/channels"

import type { ScheduledResearchPreviewResponse } from "../types"

export type PreviewStatus = "idle" | "initiating" | "streaming" | "complete" | "error"

interface UsePreviewStreamResult {
  status: PreviewStatus
  text: string
  errorMessage: string | null
  start: (prompt: string) => Promise<void>
  reset: () => void
}

export function usePreviewStream(): UsePreviewStreamResult {
  const { user } = useCurrentUser()
  const [status, setStatus] = useState<PreviewStatus>("idle")
  const [text, setText] = useState("")
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const tokenRef = useRef(0)

  const reset = useCallback(() => {
    tokenRef.current += 1
    setPreviewId(null)
    setText("")
    setErrorMessage(null)
    setStatus("idle")
  }, [])

  const start = useCallback(async (prompt: string) => {
    const token = ++tokenRef.current
    setText("")
    setErrorMessage(null)
    setStatus("initiating")
    setPreviewId(null)

    try {
      const response = await apiFetch<ScheduledResearchPreviewResponse>("/api/scheduled_research/preview", {
        method: "POST",
        body: JSON.stringify({ prompt }),
      })
      if (tokenRef.current !== token) return
      setPreviewId(response.preview_id)
      setStatus("streaming")
    } catch {
      if (tokenRef.current !== token) return
      setStatus("error")
      setErrorMessage("Couldn't start the preview. Please try again.")
    }
  }, [])

  useChannel(
    previewId && user?.id
      ? { stream: ChannelStream.SCHEDULED_RESEARCH_PREVIEW, params: { preview_id: previewId, user_id: user.id } }
      : null,
    ChannelEventResource.SCHEDULED_RESEARCH_PREVIEW,
    (_action, data) => {
      const previewAction = data.preview_action as string | undefined
      if (previewAction === "delta") {
        const delta = typeof data.text === "string" ? data.text : ""
        if (delta) setText(prev => prev + delta)
      } else if (previewAction === "complete") {
        setStatus("complete")
      } else if (previewAction === "error") {
        setStatus("error")
        setErrorMessage(typeof data.error === "string" ? data.error : "An error occurred.")
      }
    }
  )

  useEffect(() => {
    return () => {
      tokenRef.current += 1
    }
  }, [])

  return { status, text, errorMessage, start, reset }
}
