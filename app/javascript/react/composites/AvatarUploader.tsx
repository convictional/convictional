import { type ChangeEvent, useRef, useState } from "react"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { refreshCurrentUser } from "~/react/shared/stores/currentUser"
import { showFlash } from "~/shared/flash"

// The subset of the profile the avatar endpoints return that this control reads back.
export interface AvatarUpdate {
  picture: string | null
  has_custom_avatar: boolean
}

interface AvatarUploaderProps {
  picture: string | null
  hasCustomAvatar: boolean
  displayName: string
  onUpdated: (update: AvatarUpdate) => void
}

const AVATAR_ENDPOINT = "/api/users/me/profile/avatar"

// The 64px avatar with a hover "Change" overlay (click anywhere to pick a file)
// and a "Reset" affordance when a custom avatar is set. Upload POSTs multipart
// FormData — apiFetch passes a FormData body through untouched, so the browser
// sets the multipart boundary itself. The nav avatar reads the cached currentUser
// store, so refresh it after a change to update the nav without a navigation.
export function AvatarUploader({ picture, hasCustomAvatar, displayName, onUpdated }: AvatarUploaderProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  // Object URL shown immediately on file select so the new image appears before
  // the upload round-trips; replaced by the server picture on success.
  const [preview, setPreview] = useState<string | null>(null)

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Reset the input so re-selecting the same file fires change again.
    event.target.value = ""
    if (!file) return

    const previewUrl = URL.createObjectURL(file)
    setPreview(previewUrl)
    setBusy(true)
    try {
      const body = new FormData()
      body.append("avatar", file)
      const updated = await apiFetch<AvatarUpdate>(
        AVATAR_ENDPOINT,
        { method: "POST", body },
        { expectedStatuses: [422] }
      )
      onUpdated(updated)
      void refreshCurrentUser()
      showFlash("Your picture has been updated.", "success")
    } catch (error) {
      // 422 is the only rejection that's about the file itself (bad type / too
      // large); anything else (network, 5xx) gets the generic retry message.
      const message =
        error instanceof ApiError && error.status === 422
          ? "Could not update your picture. Please use a JPEG, PNG, or WebP under 5MB."
          : "Could not update your picture. Please try again."
      showFlash(message, "error")
    } finally {
      setBusy(false)
      setPreview(null)
      URL.revokeObjectURL(previewUrl)
    }
  }

  async function handleReset() {
    setBusy(true)
    try {
      await apiFetch(AVATAR_ENDPOINT, { method: "DELETE" })
    } catch {
      showFlash("Could not reset your picture. Please try again.", "error")
      setBusy(false)
      return
    }
    // The reset is persisted now. The follow-up GET only refreshes the UI with the
    // fallback picture (DELETE returns 204, no body); a failure here doesn't undo
    // the reset, so it must not surface as a reset failure — it reconciles on reload.
    try {
      onUpdated(await apiFetch<AvatarUpdate>("/api/users/me/profile"))
      void refreshCurrentUser()
    } catch {
      // best-effort UI refresh; the reset already succeeded server-side
    }
    showFlash("Your picture has been reset.", "success")
    setBusy(false)
  }

  const shown = preview ?? picture

  return (
    <div className="flex flex-col items-center gap-2 shrink-0">
      <button
        type="button"
        className="group relative block w-16 h-16 cursor-pointer rounded-full"
        onClick={() => fileInputRef.current?.click()}
        disabled={busy}
        aria-label="Change your picture"
      >
        {shown ? (
          <img
            className="w-16 h-16 rounded-full object-cover bg-base-300 transition group-hover:opacity-60"
            src={shown}
            alt={displayName}
          />
        ) : (
          <div className="w-16 h-16 rounded-full bg-base-300 transition group-hover:opacity-60" />
        )}
        <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 transition group-hover:opacity-100">
          <span className="text-xs font-medium text-white">Change</span>
        </div>
      </button>
      <input
        ref={fileInputRef}
        type="file"
        name="avatar"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={handleFileChange}
      />
      {hasCustomAvatar && (
        <button
          type="button"
          className="text-xs opacity-60 hover:opacity-100 hover:underline"
          onClick={handleReset}
          disabled={busy}
        >
          Reset
        </button>
      )}
    </div>
  )
}
