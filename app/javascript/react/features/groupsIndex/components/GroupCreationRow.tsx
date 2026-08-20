import { useEffect, useRef, useState } from "react"

import type { GroupRow } from "~/react/features/groupsIndex/types"
import { apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

interface GroupCreationRowProps {
  onCreated: (group: GroupRow) => void
  onCancel: () => void
}

export function GroupCreationRow({ onCreated, onCancel }: GroupCreationRowProps) {
  const [name, setName] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  async function submit() {
    const trimmed = name.trim()
    if (!trimmed || submitting) return

    setSubmitting(true)
    try {
      const group = await apiFetch<GroupRow>("/api/groups", {
        method: "POST",
        body: JSON.stringify({ name: trimmed }),
      })
      onCreated(group)
      setName("")
    } catch {
      showFlash("Couldn't create the group.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      className="flex gap-2 items-center mb-3"
      onSubmit={e => {
        e.preventDefault()
        submit()
      }}
    >
      <input
        ref={inputRef}
        type="text"
        value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Escape") onCancel()
        }}
        placeholder="Group name"
        className="input input-sm bg-base-200 flex-1"
        required
      />
      <button type="submit" className="btn btn-sm btn-primary" disabled={submitting}>
        Create
      </button>
      <button type="button" className="btn btn-sm btn-ghost" onClick={onCancel}>
        Cancel
      </button>
    </form>
  )
}
