import { useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

import type { MeetingDetail, RecordingUploadTarget } from "../types"

interface VideoUploadFormProps {
  meetingId: string
  onUploaded: (meeting: MeetingDetail) => void
}

// Uploads the recording browser-direct to storage (GCS in prod) so the video
// never transits the app: (1) mint a signed POST target, (2) upload the file
// straight to it, (3) PATCH the meeting with the returned object key. The
// returned meeting has recording_id set, so the parent swaps this form for the
// player. The step-2 POST is cross-origin to GCS, so it uses a plain fetch (no
// CSRF/credentials) and relies on the bucket CORS allowing POST.
export function VideoUploadForm({ meetingId, onUploaded }: VideoUploadFormProps) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [uploading, setUploading] = useState(false)

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const target = await apiFetch<RecordingUploadTarget>(`/api/meetings/${meetingId}/recording/upload_url`, {
        method: "POST",
      })

      const formData = new FormData()
      for (const [name, value] of Object.entries(target.fields)) {
        formData.append(name, value)
      }
      // GCS signed-POST policies require the file part to come last.
      formData.append("file", file)
      const uploadResponse = await fetch(target.action, { method: "POST", body: formData })
      if (!uploadResponse.ok) throw new Error(`Storage upload failed with status ${uploadResponse.status}`)

      const updated = await apiFetch<MeetingDetail>(`/api/meetings/${meetingId}`, {
        method: "PATCH",
        body: JSON.stringify({ recording_key: target.key }),
      })
      showFlash("Recording uploaded successfully.", "success")
      onUploaded(updated)
    } catch {
      showFlash("Couldn't upload the recording. Please try again.", "error")
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  return (
    <div className="w-full h-full bg-base-50 flex flex-col items-center justify-center p-4">
      <span className="material-symbols-outlined text-6xl text-base-400">videocam_off</span>
      <p className="text-sm opacity-50 text-pretty mb-2">This meeting doesn&apos;t have a video recording</p>
      <label className="btn border border-neutral">
        {uploading ? (
          <>
            <span className="loading loading-spinner loading-xs" />
            Uploading…
          </>
        ) : (
          "Upload recording"
        )}
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4"
          className="hidden"
          disabled={uploading}
          onChange={event => void handleFile(event)}
        />
      </label>
    </div>
  )
}
