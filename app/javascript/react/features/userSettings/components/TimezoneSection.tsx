import { useState } from "react"

import { SaveForm } from "~/react/composites/settings/SaveForm"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

import { TIMEZONES } from "../timezones"
import type { Profile } from "../types"

// When the user has no saved zone, preselect the browser's zone — even if it's
// not in the curated list (it's then prepended as its own option).
function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

export function TimezoneSection({ initialTimeZone }: { initialTimeZone: string | null }) {
  const [timeZone, setTimeZone] = useState(initialTimeZone ?? browserTimeZone())

  // Prepend the selected zone as its own option when it isn't one of the curated
  // values, so an uncurated saved/browser zone still shows (and stays selected).
  const options = TIMEZONES.some(option => option.value === timeZone)
    ? TIMEZONES
    : [{ value: timeZone, label: timeZone }, ...TIMEZONES]

  async function save() {
    const updated = await apiFetch<Profile>("/api/users/me/profile", {
      method: "PATCH",
      body: JSON.stringify({ time_zone: timeZone }),
    })
    if (updated.time_zone) setTimeZone(updated.time_zone)
    showFlash("Your timezone has been saved.", "success")
  }

  return (
    <SettingsSection title="Timezone" description="Used to localize schedules and times throughout the app.">
      <SaveForm onSave={save} errorMessage="Could not save your timezone. Please try again.">
        <div className="fieldset">
          <label className="label" htmlFor="profile_time_zone">
            <span className="label-text">Timezone</span>
          </label>
          <select
            className="select w-full bg-base-200"
            id="profile_time_zone"
            name="time_zone"
            value={timeZone}
            onChange={e => setTimeZone(e.target.value)}
          >
            {options.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </SaveForm>
    </SettingsSection>
  )
}
