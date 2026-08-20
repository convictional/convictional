import { type FormEvent, useState } from "react"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { SubmitButton } from "~/react/ui/SubmitButton"
import { showFlash } from "~/shared/flash"

import type { OrganizationUser } from "../types"

// Email + optional note → POST /api/organization/users. A brand-new user is
// 201, re-inviting an existing member 200 (a restore); both succeed here.
export function InviteForm({ onInvited }: { onInvited: (user: OrganizationUser) => void }) {
  const [email, setEmail] = useState("")
  const [note, setNote] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      // 201 for a new user, 200 when re-inviting/restoring an existing member;
      // either way the response is the member, which we upsert into the list.
      const invited = await apiFetch<OrganizationUser>(
        "/api/organization/users",
        { method: "POST", body: JSON.stringify({ email, note }) },
        { expectedStatuses: [422] }
      )
      setEmail("")
      setNote("")
      showFlash("Invite sent.", "success")
      onInvited(invited)
    } catch (err) {
      // 422 carries a meaningful, user-facing reason (banned domain, belongs to
      // another org), so surface it rather than a generic message.
      const detail = err instanceof ApiError && typeof err.body?.detail === "string" ? err.body.detail : null
      showFlash(detail ?? "Could not send the invite. Please try again.", "error")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <input
        type="email"
        name="email"
        placeholder="Type their email..."
        required
        value={email}
        onChange={e => setEmail(e.target.value)}
        className="input w-full bg-base-200 placeholder-base-500"
      />
      <textarea
        name="note"
        placeholder="Add a personal note to the invitation..."
        value={note}
        onChange={e => setNote(e.target.value)}
        className="textarea w-full bg-base-200 placeholder-base-500"
      />
      <div className="flex justify-end">
        <SubmitButton submitting={submitting} className="btn btn-primary">
          Invite
        </SubmitButton>
      </div>
    </form>
  )
}
