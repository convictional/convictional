import { useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { apiFetch } from "~/react/shared/apiFetch"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { showFlash } from "~/shared/flash"

interface DeleteButtonProps {
  meetingId: string
}

export function DeleteButton({ meetingId }: DeleteButtonProps) {
  const [pending, setPending] = useState(false)

  async function handleClick() {
    const confirmed = await confirm({
      title: "Delete meeting?",
      message: "This will delete the meeting and its transcript. This action cannot be undone.",
      confirmLabel: "Delete",
    })
    if (!confirmed) return
    setPending(true)
    try {
      await apiFetch(`/api/meetings/${meetingId}`, { method: "DELETE" })
      boostedNavigate("/meetings")
    } catch {
      showFlash("Couldn't delete the meeting. Please try again.", "error")
      setPending(false)
    }
  }

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={pending}
      className="btn btn-square"
      aria-label="Delete meeting"
    >
      <span className="material-symbols-outlined text-lg">delete</span>
    </button>
  )
}
