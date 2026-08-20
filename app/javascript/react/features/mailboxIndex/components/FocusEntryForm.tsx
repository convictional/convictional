import { type FormEvent, useState } from "react"

// One modal form for both Focus entry kinds, so creating or editing a custom view and a custom
// sort feel like first-class peers. A view groups threads into labeled sections (layout=grouped);
// a sort ranks them into a single list (layout=ranked). The structure is shared; only the copy and
// suggestions differ by kind. The `criteria` field maps to the backend `view_request`; the title is
// optional (the server auto-generates one from the request when left blank).
//
// Styling follows the research / search overlays: a borderless hero textarea, subtle text
// suggestion chips, and a soft divider above the action bar. The surrounding floating-card is
// passed `!p-0`, so this form owns its padding.

export type FocusEntryKind = "view" | "sort"

// Prefill for the edit flow. Sourced from a saved MailboxViewSummary by the caller
// (`criteria` <- `view_request`); null when creating.
export interface FocusEntryEdit {
  title: string
  criteria: string
}

interface FormCopy {
  newTitle: string
  editTitle: string
  placeholder: string
  helper: string
  submit: string
  suggestions: { label: string; value: string }[]
}

const COPY: Record<FocusEntryKind, FormCopy> = {
  view: {
    newTitle: "New custom view",
    editTitle: "Edit custom view",
    placeholder: "How should your inbox be grouped?",
    helper: "Groups threads into labeled sections — by topic, sender, goal, or any rule you can describe.",
    submit: "Create view",
    suggestions: [
      { label: "Needs reply", value: "Group emails that need a reply, separate from everything else" },
      { label: "By sender", value: "Group by sender, separating my team from external people" },
      { label: "By goal", value: "Organize threads under each of my goals" },
      { label: "Urgent vs. later", value: "Split into what's urgent now versus what can wait" },
    ],
  },
  sort: {
    newTitle: "New custom sort",
    editTitle: "Edit custom sort",
    placeholder: "How should your inbox be ordered?",
    helper: "Ranks every thread into one list — by urgency, sender, age, or any rule you can describe.",
    submit: "Create sort",
    suggestions: [
      { label: "Urgency", value: "Order by how time-sensitive each thread is" },
      { label: "Sender importance", value: "Put messages from leadership and key clients first" },
      { label: "Quick wins", value: "Surface the fastest replies I can knock out first" },
      { label: "Longest waiting", value: "Order by how long someone has been waiting on my reply" },
    ],
  },
}

interface FocusEntryFormProps {
  kind: FocusEntryKind
  editingEntry: FocusEntryEdit | null
  onSave: (params: { criteria: string; title: string }) => Promise<void>
  onCancel: () => void
}

export function FocusEntryForm({ kind, editingEntry, onSave, onCancel }: FocusEntryFormProps) {
  const copy = COPY[kind]
  const isEditing = editingEntry !== null
  const [criteria, setCriteria] = useState(editingEntry?.criteria ?? "")
  const [title, setTitle] = useState(editingEntry?.title ?? "")
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const trimmed = criteria.trim()
    // Guard on `saving` too: onSave navigates on success, so a double-click could otherwise fire
    // two concurrent create/update mutations before the page leaves.
    if (!trimmed || saving) return
    setSaving(true)
    try {
      // Leave the title blank when unnamed — the views endpoint auto-generates one from the request.
      await onSave({ criteria: trimmed, title: title.trim() })
    } finally {
      setSaving(false)
    }
  }

  const fieldClasses =
    "w-full rounded-xl border border-base-400/70 bg-base-100 placeholder:text-base-content/40 transition focus:border-primary/50 focus:outline-hidden focus:ring-2 focus:ring-primary/20"

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-6" data-test-id="focus-entry-form">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-base-content">{isEditing ? copy.editTitle : copy.newTitle}</h2>
        {!isEditing && <p className="text-xs text-base-content/50">{copy.helper}</p>}
      </div>

      <div className="flex flex-col gap-2">
        <textarea
          value={criteria}
          onChange={e => setCriteria(e.target.value)}
          className={`${fieldClasses} min-h-[96px] resize-none px-4 py-3 text-base leading-relaxed`}
          placeholder={copy.placeholder}
          rows={3}
          required
          autoFocus
        />
        {!isEditing && (
          <div className="flex flex-wrap items-center gap-1.5">
            {copy.suggestions.map(suggestion => (
              <button
                key={suggestion.label}
                type="button"
                className="cursor-pointer rounded-full border border-base-400/60 px-3 py-1 text-xs text-base-content/70 transition-colors hover:border-base-400 hover:bg-base-200 hover:text-base-content"
                onClick={() => setCriteria(suggestion.value)}
              >
                {suggestion.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <input
        type="text"
        value={title}
        onChange={e => setTitle(e.target.value)}
        className={`${fieldClasses} px-4 py-2.5 text-sm`}
        placeholder="Name (optional)"
      />

      <div className="flex items-center justify-end gap-2">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={!criteria.trim() || saving}>
          {isEditing ? "Save" : copy.submit}
        </button>
      </div>
    </form>
  )
}
