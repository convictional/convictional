import { useRef, useState } from "react"

import { apiFetch, errorMessage } from "~/react/shared/apiFetch"
import type { MeetingResponse } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"

interface UploadTranscriptFormProps {
  onCreated: (meeting: MeetingResponse) => void
}

// "Upload transcript" toolbar action. Reads the chosen file as text in the
// browser, then POSTs to `/api/meetings` with `type: "transcript"`. The
// server enqueues ProcessTranscriptJob and we hand the caller the created
// meeting.
export function UploadTranscriptForm({ onCreated }: UploadTranscriptFormProps) {
  const [open, setOpen] = useState(false)
  const [transcript, setTranscript] = useState("")
  const [pending, setPending] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function reset() {
    setOpen(false)
    setTranscript("")
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setTranscript(await file.text())
    } catch {
      showFlash("Failed to read the selected file.", "error")
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!transcript.trim()) return
    setPending(true)
    try {
      const created = await apiFetch<MeetingResponse>("/api/meetings", {
        method: "POST",
        body: JSON.stringify({ type: "transcript", transcript }),
      })
      onCreated(created)
      reset()
    } catch (e) {
      showFlash(errorMessage(e, "Failed to upload transcript."), "error")
    } finally {
      setPending(false)
    }
  }

  if (!open) {
    return (
      <button type="button" className="btn" onClick={() => setOpen(true)} aria-label="Upload transcript">
        <span className="material-symbols-outlined text-base">upload</span>
        Upload transcript
      </button>
    )
  }

  return (
    <form onSubmit={submit} className="flex items-center gap-2">
      <input
        ref={fileInputRef}
        type="file"
        accept=".txt,.rtf,.vtt"
        onChange={onFileChange}
        className="file-input file-input-sm"
      />
      <button type="submit" className="btn btn-sm btn-neutral" disabled={pending || !transcript.trim()}>
        Create
      </button>
      <button type="button" className="btn btn-sm btn-ghost" onClick={reset}>
        Cancel
      </button>
    </form>
  )
}
