import { useEffect, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"

interface ConnectionStatus<T> {
  data: T | null
  setData: (data: T) => void
  loading: boolean
  error: boolean
}

// Fetch an integration's connection-status resource once on mount, exposing
// loading/error flags plus a setter so a section can apply an optimistic update
// after a disconnect. The Gmail, Slack, and Notion sections each read their own
// status endpoint through this; calendar uses the richer useCalendarConnection.
export function useConnectionStatus<T>(url: string): ConnectionStatus<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiFetch<T>(url)
      .then(result => {
        if (!cancelled) setData(result)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [url])

  return { data, setData, loading, error }
}
