import { useState } from "react"

import { AvatarUploader, type AvatarUpdate } from "~/react/composites/AvatarUploader"
import { SaveForm } from "~/react/composites/settings/SaveForm"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { apiFetch } from "~/react/shared/apiFetch"
import { NAME_MAX_LENGTH, NAME_PATTERN, NAME_TITLE } from "~/react/shared/nameValidation"
import { refreshCurrentUser } from "~/react/shared/stores/currentUser"
import { showFlash } from "~/shared/flash"

import type { Profile } from "../types"

// Avatar + display name — the user's public identity. Seeded from the parent's
// GET /api/users/me/profile. The name saves via PATCH; the avatar has its own
// POST/DELETE pipeline in AvatarUploader. Both refresh the cached currentUser so
// the nav updates without a navigation.
export function ProfileSection({ profile }: { profile: Profile }) {
  const [name, setName] = useState(profile.name ?? "")
  const [picture, setPicture] = useState(profile.picture)
  const [hasCustomAvatar, setHasCustomAvatar] = useState(profile.has_custom_avatar)

  function applyProfile(updated: AvatarUpdate) {
    setPicture(updated.picture)
    setHasCustomAvatar(updated.has_custom_avatar)
  }

  async function save() {
    const updated = await apiFetch<Profile>("/api/users/me/profile", {
      method: "PATCH",
      body: JSON.stringify({ name }),
    })
    setName(updated.name ?? "")
    void refreshCurrentUser()
    showFlash("Your name has been saved.", "success")
  }

  return (
    <SettingsSection title="Profile" description="Your picture and name as they appear throughout the app.">
      <div className="flex items-start gap-5">
        <AvatarUploader
          picture={picture}
          hasCustomAvatar={hasCustomAvatar}
          displayName={name || "Your avatar"}
          onUpdated={applyProfile}
        />
        <div className="flex-1">
          <SaveForm onSave={save} errorMessage="Could not save your name. Please try again.">
            <div className="fieldset">
              <label className="label" htmlFor="profile_name">
                <span className="label-text">Name</span>
              </label>
              <input
                className="input input-sm w-full bg-base-200 placeholder-base-500"
                id="profile_name"
                name="name"
                type="text"
                required
                maxLength={NAME_MAX_LENGTH}
                pattern={NAME_PATTERN}
                title={NAME_TITLE}
                placeholder="Your name"
                value={name}
                onChange={e => setName(e.target.value.normalize("NFC"))}
              />
            </div>
          </SaveForm>
        </div>
      </div>
    </SettingsSection>
  )
}
