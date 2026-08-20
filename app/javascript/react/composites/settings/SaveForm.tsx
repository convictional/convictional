import { type FormEvent, type ReactNode, useState } from "react"

import { SubmitButton } from "~/react/ui/SubmitButton"

interface SaveFormProps {
  // The save side effect (PATCH + success flash). Throwing surfaces errorMessage
  // inline; the lifecycle (saving/error reset) is owned here.
  onSave: () => Promise<void>
  errorMessage: string
  children: ReactNode
}

// Shared chrome for singleton-PATCH settings sections across settings islands:
// the saving/error lifecycle, the right-aligned Save button, and the inline
// error. Each section supplies its fields as children and the save side effect.
export function SaveForm({ onSave, errorMessage, children }: SaveFormProps) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await onSave()
    } catch {
      setError(errorMessage)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {children}
      <div className="flex justify-end mt-4">
        <SubmitButton submitting={saving} className="btn bg-base-200 border border-neutral">
          Save
        </SubmitButton>
      </div>
      {error && (
        <div role="alert" className="text-xs text-error-content mt-2 text-right">
          {error}
        </div>
      )}
    </form>
  )
}
