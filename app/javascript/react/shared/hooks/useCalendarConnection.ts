import { useCallback, useEffect, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { CalendarResponse } from "~/react/shared/types"

// The current user's Recall.AI calendar connection: status plus the recording
// preference (PATCH) and disconnect (DELETE) mutations. Connect is a full-document
// navigation to the Google OAuth route, so it isn't owned here. Shared by the
// meetings upcoming index (status only) and the user-settings calendar section.
export function useCalendarConnection() {
  const [calendar, setCalendar] = useState<CalendarResponse | null>(null)
  // `loading` lets callers hold off on the empty state until the connection
  // state is known, so the Connect-Calendar prompt doesn't flash in after a
  // momentary "No upcoming meetings".
  const [loading, setLoading] = useState(true)
  // `error` lets callers that own the whole connection UI (the settings section)
  // show an error state. The meetings index ignores it and treats a failure as
  // "unknown state" — hiding its optional prompt is better than blocking.
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiFetch<CalendarResponse>("/api/users/me/calendar")
      .then(data => {
        if (!cancelled) setCalendar(data)
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
  }, [])

  const updatePreference = useCallback(async (preference: CalendarResponse["preference"]) => {
    const updated = await apiFetch<CalendarResponse>("/api/users/me/calendar", {
      method: "PATCH",
      body: JSON.stringify({ preference }),
    })
    setCalendar(updated)
  }, [])

  const disconnect = useCallback(async () => {
    await apiFetch("/api/users/me/calendar", { method: "DELETE" })
    // DELETE returns 204. Flip the connection locally rather than refetching:
    // is_google_authenticated (which gates the connect prompt) is unchanged by a
    // disconnect, and the connection-specific fields are cleared. Avoids an extra
    // round-trip and the "disconnect succeeded but the refetch failed" error path.
    setCalendar(prev =>
      prev ? { ...prev, calendar_connected: false, provider: null, preference: "none", calendar_user_id: null } : prev
    )
  }, [])

  return { calendar, loading, error, updatePreference, disconnect }
}
