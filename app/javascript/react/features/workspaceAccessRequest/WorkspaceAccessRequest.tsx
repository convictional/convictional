import { useRef, useState } from "react"

import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { DateTime } from "~/react/ui/DateTime"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { useWorkspaceAccessRequest } from "./hooks/useWorkspaceAccessRequest"
import type { WorkspaceAccessRequestProps } from "./types"

export function WorkspaceAccessRequest({ workspaceId, backUrl }: WorkspaceAccessRequestProps) {
  const { loading, error, resourceLabel, request, submit, submitting } = useWorkspaceAccessRequest(workspaceId)
  const [note, setNote] = useState("")
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Boost the backUrl link so returning is a same-realm nav, not a hard reload
  // that strands the realm (#8744). The link lives in whichever branch renders,
  // so re-process when the branch switches.
  const rootRef = useRef<HTMLElement>(null)
  useBoostIslandLinks(rootRef, [loading, error, request])

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} />

  if (request) {
    return (
      <div ref={rootRef as React.RefObject<HTMLDivElement>} className="flex flex-col items-center gap-4">
        <h1 className="font-bold text-3xl">Access requested</h1>
        <p>
          Your access request was sent <DateTime datetime={request.created_at} format="relative" />
        </p>
        <div className="flex justify-start">
          <a href={backUrl} className="btn btn-ghost btn-sm">
            ← Back
          </a>
        </div>
      </div>
    )
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitError(null)
    try {
      const response = await submit(note)
      if (response.redirect_url) {
        boostedNavigate(response.redirect_url)
      }
    } catch {
      setSubmitError("There was a problem sending your request. Please try again.")
    }
  }

  return (
    <form
      ref={rootRef as React.RefObject<HTMLFormElement>}
      onSubmit={onSubmit}
      className="flex flex-col items-center gap-4 w-full"
    >
      <h1 className="font-bold text-3xl">Request access</h1>
      <p>Ask to become a collaborator on this {resourceLabel}</p>
      <div className="fieldset w-full">
        <textarea
          className="textarea h-24 w-full"
          name="note"
          placeholder="Optional note for the current team"
          value={note}
          onChange={event => setNote(event.target.value)}
          disabled={submitting}
        />
      </div>
      {submitError && <p className="text-error text-sm">{submitError}</p>}
      <div className="flex justify-center mt-4 gap-4">
        <a href={backUrl} className="btn btn-ghost">
          Nevermind
        </a>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          Request access
        </button>
      </div>
    </form>
  )
}
