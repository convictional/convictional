import { type KeyboardEvent, useEffect, useRef, useState } from "react"

import { ApiError, errorMessage } from "~/react/shared/apiFetch"
import { SubmitButton } from "~/react/ui/SubmitButton"
import { createQuickLink, deleteQuickLink, fetchQuickLink, updateQuickLink } from "../api"
import type { QuickLink } from "../types"

interface QuickLinkFormProps {
  quickLinkId: string | null
  onSaved: () => void
  onDeleted: () => void
}

interface FormValues {
  label: string
  url: string
  open_in_new_tab: boolean
}

const BLANK_VALUES: FormValues = {
  label: "",
  url: "",
  open_in_new_tab: true,
}

// Swallow keys the parent palette consumes globally so they fire inside the form instead.
function swallowPaletteShortcuts(event: KeyboardEvent<HTMLElement>): void {
  const keys = ["Enter", "ArrowUp", "ArrowDown", "Backspace", "Delete"]
  if (keys.includes(event.key)) event.stopPropagation()
}

export function QuickLinkForm({ quickLinkId, onSaved, onDeleted }: QuickLinkFormProps) {
  const isEditing = quickLinkId !== null
  const [values, setValues] = useState<FormValues>(BLANK_VALUES)
  const [loaded, setLoaded] = useState(!isEditing)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const labelRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!quickLinkId) return
    const controller = new AbortController()
    fetchQuickLink(quickLinkId, controller.signal)
      .then((link: QuickLink) => {
        setValues({ label: link.label, url: link.url, open_in_new_tab: link.open_in_new_tab })
        setLoaded(true)
      })
      .catch(() => setError("Couldn't load quick link."))
    return () => controller.abort()
  }, [quickLinkId])

  useEffect(() => {
    if (loaded) labelRef.current?.focus()
  }, [loaded])

  const submit = async () => {
    if (submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const payload = {
        label: values.label.trim(),
        url: values.url.trim(),
        open_in_new_tab: values.open_in_new_tab,
      }
      if (quickLinkId) {
        await updateQuickLink(quickLinkId, payload)
      } else {
        await createQuickLink(payload)
      }
      onSaved()
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setError("Please provide a valid HTTP or HTTPS URL.")
      } else {
        setError(errorMessage(err, "Couldn't save quick link."))
      }
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!quickLinkId) return
    setSubmitting(true)
    setError(null)
    try {
      await deleteQuickLink(quickLinkId)
      onDeleted()
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete quick link."))
      setSubmitting(false)
    }
  }

  if (!loaded) {
    return <div className="p-4 py-2 text-sm text-base-500">Loading…</div>
  }

  return (
    <div className="p-4 py-2 grid gap-3" data-test-id="quick-link-form">
      <div>
        <p className="text-xs text-base-500 pb-2">{isEditing ? `Edit ${values.label}` : "Create a quick link"}</p>
        <span className="text-xs text-base-600/70 inline-flex items-center gap-1">
          Quick links allow you to quickly navigate to your favorite pages.
        </span>
      </div>
      <form
        onSubmit={e => {
          e.preventDefault()
          submit()
        }}
        onKeyDown={swallowPaletteShortcuts}
        className="grid gap-2"
      >
        <fieldset className="fieldset">
          <legend className="fieldset-legend">Command</legend>
          <div className="input w-full inline-flex items-baseline gap-1 bg-base-200 border-none focus:outline-none focus-within:outline-none">
            <span className="text-base-400">/</span>
            <input
              ref={labelRef}
              type="text"
              autoComplete="off"
              name="label"
              className="w-full"
              placeholder="label"
              value={values.label}
              onChange={e => setValues({ ...values, label: e.target.value })}
            />
          </div>
          <p className="label">This is what you'll type to launch the quick link</p>
        </fieldset>
        <fieldset className="fieldset">
          <legend className="fieldset-legend">Page to open</legend>
          <div className="input w-full inline-flex items-baseline gap-1 bg-base-200 border-none focus:outline-none focus-within:outline-none">
            <input
              type="text"
              autoComplete="off"
              name="url"
              className="w-full"
              placeholder="https://example.com"
              value={values.url}
              onChange={e => setValues({ ...values, url: e.target.value })}
            />
          </div>
        </fieldset>
        <div className="flex items-end justify-between">
          <fieldset className="fieldset">
            <legend className="fieldset-legend">Behavior</legend>
            <label className="label cursor-pointer">
              <input
                type="checkbox"
                className="toggle toggle-primary"
                checked={values.open_in_new_tab}
                onChange={e => setValues({ ...values, open_in_new_tab: e.target.checked })}
              />
              <span className={values.open_in_new_tab ? "text-base-900" : ""}>
                {values.open_in_new_tab ? "Open in new tab" : "Open in new tab?"}
              </span>
            </label>
          </fieldset>
          {isEditing ? (
            <div className="flex items-end justify-end gap-2">
              <button
                type="button"
                onClick={handleDelete}
                disabled={submitting}
                className="btn btn-outline btn-danger"
              >
                Delete
              </button>
              <SubmitButton submitting={submitting}>Save</SubmitButton>
            </div>
          ) : (
            <SubmitButton submitting={submitting}>Create quick link</SubmitButton>
          )}
        </div>
        {error && <p className="text-xs text-error">{error}</p>}
      </form>
    </div>
  )
}
