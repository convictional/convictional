import { useState } from "react"

import { SaveForm } from "~/react/composites/settings/SaveForm"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

import type { Profile } from "../types"

// Free-text job description / bio. Seeded from the parent's profile fetch, saved
// via PATCH { bio }.
export function BioSection({ initialBio }: { initialBio: string | null }) {
  const [bio, setBio] = useState(initialBio ?? "")

  async function save() {
    const updated = await apiFetch<Profile>("/api/users/me/profile", {
      method: "PATCH",
      body: JSON.stringify({ bio }),
    })
    setBio(updated.bio ?? "")
    showFlash("Your job description has been saved.", "success")
  }

  return (
    <SettingsSection
      title="Job Description"
      description="Share what you do, your key responsibilities, and areas of expertise."
    >
      <SaveForm onSave={save} errorMessage="Could not save your job description. Please try again.">
        <div className="fieldset">
          <label className="label" htmlFor="profile_bio">
            <span className="label-text">Job description</span>
          </label>
          <textarea
            className="textarea w-full bg-base-200 placeholder-base-500"
            id="profile_bio"
            name="bio"
            rows={3}
            required
            placeholder="Share what you do, your key responsibilities, and areas of expertise."
            value={bio}
            onChange={e => setBio(e.target.value)}
          />
        </div>
      </SaveForm>
    </SettingsSection>
  )
}
