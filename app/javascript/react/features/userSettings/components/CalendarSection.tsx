import { useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { useCalendarConnection } from "~/react/shared/hooks/useCalendarConnection"
import type { CalendarResponse } from "~/react/shared/types"
import { ErrorState } from "~/react/ui/ErrorState"
import { GoogleCalendarLogo } from "~/react/ui/GoogleCalendarLogo"
import { LoadingState } from "~/react/ui/LoadingState"
import { showFlash } from "~/shared/flash"

const DESCRIPTION = "Connect your calendar to import and record meetings automatically."

// Connect is a full-document navigation to the Google Calendar OAuth route, which
// returns to the page named in return_to (defaulting to the app home, so we set it
// to /profile/edit explicitly), not an <a>.
const CONNECT_URL = `/integrations/google_calendar/login?return_to=${encodeURIComponent("/profile/edit")}`

export function CalendarSection() {
  const { calendar, loading, error, updatePreference, disconnect } = useCalendarConnection()
  const [saving, setSaving] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)

  async function changePreference(preference: CalendarResponse["preference"]) {
    setSaving(true)
    try {
      await updatePreference(preference)
      showFlash("Your recording preference has been saved.", "success")
    } catch {
      showFlash("Could not save your recording preference. Please try again.", "error")
    } finally {
      setSaving(false)
    }
  }

  async function handleDisconnect() {
    const confirmed = await confirm({ message: "Are you sure you want to disconnect your calendar?" })
    if (!confirmed) return
    setDisconnecting(true)
    try {
      await disconnect()
      showFlash("Your calendar has been disconnected.", "success")
    } catch {
      showFlash("Could not disconnect your calendar. Please try again.", "error")
    } finally {
      setDisconnecting(false)
    }
  }

  function body() {
    if (loading) return <LoadingState className="py-6" />
    if (error || !calendar) return <ErrorState message="Could not load your calendar connection." />

    if (calendar.calendar_connected) {
      return (
        <>
          <div className="fieldset">
            <label className="label" htmlFor="calendar_preference">
              <span className="label-text">Automatic meeting recording</span>
            </label>
            <select
              className="select select-sm w-full bg-base-200"
              id="calendar_preference"
              value={calendar.preference}
              disabled={saving}
              onChange={e => changePreference(e.target.value as CalendarResponse["preference"])}
            >
              <option value="none">Do not automatically record my meetings</option>
              <option value="all">Automatically record all meetings on my calendar</option>
            </select>
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              className="btn bg-base-200 border border-neutral"
              disabled={disconnecting}
              onClick={handleDisconnect}
            >
              Disconnect
            </button>
          </div>
        </>
      )
    }

    if (calendar.is_google_authenticated) {
      return (
        <div className="flex justify-end">
          <button type="button" className="btn btn-primary" onClick={() => window.location.assign(CONNECT_URL)}>
            <span className="w-5">
              <GoogleCalendarLogo />
            </span>
            Connect Google Calendar
          </button>
        </div>
      )
    }

    return <p className="text-sm opacity-75">Calendar integration is not supported for your authentication method.</p>
  }

  return (
    <SettingsSection title="Calendar and Meeting Recording" description={DESCRIPTION}>
      {body()}
    </SettingsSection>
  )
}
