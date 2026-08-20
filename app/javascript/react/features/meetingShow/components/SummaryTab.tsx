import { useCallback, useState } from "react"

import { Markdown } from "~/react/composites/markdown/Markdown"
import { apiFetch } from "~/react/shared/apiFetch"

import type { MeetingDetail } from "../types"

interface SummaryTabProps {
  meeting: MeetingDetail
  onLocalUpdate: <K extends keyof MeetingDetail>(field: K, value: MeetingDetail[K]) => void
  onServerUpdate: (meeting: MeetingDetail) => void
}

export function SummaryTab({ meeting, onLocalUpdate, onServerUpdate }: SummaryTabProps) {
  const [editing, setEditing] = useState(false)
  // Only meaningful while editing — the read view renders meeting.summary
  // directly, so we seed draft when entering edit mode rather than keeping
  // the two in sync with an effect.
  const [draft, setDraft] = useState("")

  // Summary persists only on an explicit Save, so Cancel can discard the draft
  // without leaving a half-saved server value.
  const save = useCallback(
    async (value: string) => {
      onLocalUpdate("summary", value)
      setEditing(false)
      try {
        const updated = await apiFetch<MeetingDetail>(`/api/meetings/${meeting.id}`, {
          method: "PATCH",
          body: JSON.stringify({ summary: value }),
        })
        onServerUpdate(updated)
      } catch {
        // apiFetch reports to Sentry; the optimistic local update stays so the
        // user keeps their text and can re-edit to retry.
      }
    },
    [meeting.id, onLocalUpdate, onServerUpdate]
  )

  if (!editing) {
    return (
      <div className="grid grid-cols-[1fr_auto] gap-2">
        <div>
          {meeting.summary ? (
            <Markdown source={meeting.summary} className="!max-w-none" />
          ) : (
            <p className="text-base-500 italic">No summary provided.</p>
          )}
        </div>
        <button
          type="button"
          className="self-start opacity-0 group-hover:opacity-100"
          onClick={() => {
            setDraft(meeting.summary ?? "")
            setEditing(true)
          }}
          aria-label="Edit summary"
        >
          <span className="material-symbols-outlined text-lg">edit</span>
        </button>
      </div>
    )
  }

  return (
    <div className="grid gap-2">
      <textarea
        value={draft}
        autoFocus
        rows={5}
        className="textarea w-full leading-6"
        onChange={e => setDraft(e.target.value)}
      />
      <div className="flex justify-end gap-2">
        <button type="button" className="btn" onClick={() => setEditing(false)}>
          Cancel
        </button>
        <button type="button" className="btn btn-neutral" onClick={() => void save(draft)}>
          Save
        </button>
      </div>
    </div>
  )
}
