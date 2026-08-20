import { useCallback, useEffect, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { AccessRequest, WorkspaceAccessRequestState, WorkspaceAccessRequestSubmitResponse } from "../types"

export interface UseWorkspaceAccessRequestResult {
  loading: boolean
  error: string | null
  resourceLabel: string
  request: AccessRequest | null
  submit: (note: string) => Promise<WorkspaceAccessRequestSubmitResponse>
  submitting: boolean
}

export function useWorkspaceAccessRequest(workspaceId: string): UseWorkspaceAccessRequestResult {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [resourceLabel, setResourceLabel] = useState("")
  const [request, setRequest] = useState<AccessRequest | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiFetch<WorkspaceAccessRequestState>(`/api/workspaces/${workspaceId}/collaborators/access`)
      .then(state => {
        if (cancelled) return
        setResourceLabel(state.resource_label)
        setRequest(state.request)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setError("Could not load this page.")
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId])

  const submit = useCallback(
    async (note: string) => {
      setSubmitting(true)
      try {
        const response = await apiFetch<WorkspaceAccessRequestSubmitResponse>(
          `/api/workspaces/${workspaceId}/collaborators/access`,
          { method: "POST", body: JSON.stringify({ note }) }
        )
        setRequest(response.request)
        return response
      } finally {
        setSubmitting(false)
      }
    },
    [workspaceId]
  )

  return { loading, error, resourceLabel, request, submit, submitting }
}
