import { useState } from "react"

import { apiFetch, errorMessage } from "~/react/shared/apiFetch"
import type { MeetingResponse } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"

interface StartRecordingFormProps {
  onCreated: (meeting: MeetingResponse) => void
}

// "Start recording from link" toolbar action. POSTs to `POST /api/meetings`
// with `type: "url"` and lets the caller decide what to do with the new
// meeting (the past-list navigates to it).
export function StartRecordingForm({ onCreated }: StartRecordingFormProps) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState("")
  const [pending, setPending] = useState(false)

  function reset() {
    setOpen(false)
    setUrl("")
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setPending(true)
    try {
      const created = await apiFetch<MeetingResponse>("/api/meetings", {
        method: "POST",
        body: JSON.stringify({ type: "url", conferencing_url: url.trim() }),
      })
      onCreated(created)
      reset()
    } catch (e) {
      showFlash(errorMessage(e, "Failed to start recording."), "error")
    } finally {
      setPending(false)
    }
  }

  if (!open) {
    return (
      <button type="button" className="btn" onClick={() => setOpen(true)} aria-label="Start recording from link">
        <span className="material-symbols-outlined text-base">videocam</span>
        <span className="hidden md:inline">Start recording from link</span>
      </button>
    )
  }

  return (
    <form onSubmit={submit} className="flex items-center gap-2">
      <input
        type="text"
        autoFocus
        value={url}
        onChange={e => setUrl(e.target.value)}
        placeholder="Meeting URL"
        className="input input-sm"
      />
      <button type="submit" className="btn btn-sm btn-neutral" disabled={pending || !url.trim()}>
        Record
      </button>
      <button type="button" className="btn btn-sm btn-ghost" onClick={reset}>
        Cancel
      </button>
    </form>
  )
}
