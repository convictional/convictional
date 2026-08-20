import { useState } from "react"

import { SubmitButton } from "~/react/ui/SubmitButton"

interface CollectionFormProps {
  initialTitle?: string
  initialDescription?: string
  submitLabel: string
  // Returns an error message to surface inline, or null on success. The caller
  // owns what happens next (close the dialog, leave edit mode, refresh, etc.).
  onSubmit: (title: string, description: string | null) => Promise<string | null>
  onCancel: () => void
}

export function CollectionForm({
  initialTitle = "",
  initialDescription = "",
  submitLabel,
  onSubmit,
  onCancel,
}: CollectionFormProps) {
  const [title, setTitle] = useState(initialTitle)
  const [description, setDescription] = useState(initialDescription)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim() || pending) return
    setPending(true)
    setError(null)
    const err = await onSubmit(title.trim(), description.trim() || null)
    setPending(false)
    if (err) setError(err)
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-semibold opacity-75">Title</span>
        <input
          type="text"
          autoFocus
          required
          value={title}
          onChange={e => setTitle(e.target.value)}
          className="input input-bordered"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs font-semibold opacity-75">Description (optional)</span>
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          className="textarea textarea-bordered"
          rows={3}
        />
      </label>
      {error && <p className="text-xs text-error">{error}</p>}
      <div className="flex justify-end gap-2 mt-2">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <SubmitButton submitting={pending} className="btn btn-neutral">
          {submitLabel}
        </SubmitButton>
      </div>
    </form>
  )
}
