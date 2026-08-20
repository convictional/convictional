import { useEffect, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { formatDateTime } from "~/react/ui/DateTime"
import { LoadingState } from "~/react/ui/LoadingState"

import type { MeetingChatListResponse, MeetingChatMessage } from "../types"

interface ChatTabProps {
  meetingId: string
}

export function ChatTab({ meetingId }: ChatTabProps) {
  const [messages, setMessages] = useState<MeetingChatMessage[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiFetch<MeetingChatListResponse>(`/api/meetings/${meetingId}/chat`)
      .then(res => {
        if (!cancelled) setMessages(res.messages)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [meetingId])

  if (error) return <p className="text-base-500 italic">Couldn't load in-meeting chat.</p>
  if (messages === null) {
    return <LoadingState className="py-6" />
  }
  if (messages.length === 0) {
    return <p className="text-base-500 italic">No in-meeting chat for this meeting.</p>
  }

  return (
    <ul className="space-y-1">
      {messages.map((m, idx) => (
        <li key={`${m.created_at}-${idx}`} className="p-2 space-y-2 rounded-md bg-base-100">
          <div className="flex gap-2 items-baseline">
            <span className="text-xs text-base-500">{m.sender_name}</span>
            <span className="text-xs text-base-400">{formatDateTime(m.created_at, "datetime")}</span>
          </div>
          <p className="text-xs text-base-600 whitespace-pre-wrap break-words">{m.text}</p>
        </li>
      ))}
    </ul>
  )
}
