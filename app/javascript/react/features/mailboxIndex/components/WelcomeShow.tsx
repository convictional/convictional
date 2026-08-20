import { Link } from "@tanstack/react-router"
import { useEffect, useState } from "react"

import { AvatarUploader } from "~/react/composites/AvatarUploader"
import { MAILBOX_ACTION_SEGMENT_CLASS } from "~/react/composites/MailboxActionBar"
import {
  MAILBOX_ACTION_CLUSTER_CLASS,
  MAILBOX_ACTION_DIVIDER_CLASS,
} from "~/react/composites/MailboxActionBar/segments"
import { SnoozeDropdown } from "~/react/composites/MailboxActionBar/SnoozeDropdown"
import { SaveForm } from "~/react/composites/settings/SaveForm"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { NAME_MAX_LENGTH, NAME_PATTERN, NAME_TITLE } from "~/react/shared/nameValidation"
import { refreshCurrentUser } from "~/react/shared/stores/currentUser"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { Tooltip } from "~/react/ui/Tooltip"
import { showFlash } from "~/shared/flash"

interface WelcomeProfile {
  name: string | null
  picture: string | null
  has_custom_avatar: boolean
}

interface WelcomeShowProps {
  read: boolean
  onToggleRead: () => void
  onBack: () => void
  onArchive: () => void
  onSnooze: () => void
}

// The Welcome entry opened as a mailbox show: the sticky action header (back /
// archive / read / snooze) over a "make it yours" identity form. It reuses the
// profile-edit and organization-settings building blocks — same avatar uploader,
// SaveForm, and SettingsSection — so the fields behave and read like Settings.
// Archive/snooze are local dismissals owned by the parent (nothing to persist).
export function WelcomeShow({ read, onToggleRead, onBack, onArchive, onSnooze }: WelcomeShowProps) {
  const { user } = useCurrentUser()
  const isAdmin = user?.is_admin ?? false
  // Offer org naming only to admins who haven't set a name yet (matches the WelcomeRow preview).
  const canNameOrganization = isAdmin && !user?.organization_name?.trim()

  const [profile, setProfile] = useState<WelcomeProfile | null>(null)
  const [name, setName] = useState("")
  const [company, setCompany] = useState(user?.organization_name ?? "")
  const [snoozeOpen, setSnoozeOpen] = useState(false)

  useEffect(() => {
    let active = true
    void apiFetch<WelcomeProfile>("/api/users/me/profile").then(p => {
      if (!active) return
      setProfile(p)
      setName(p.name ?? "")
    })
    return () => {
      active = false
    }
  }, [])

  async function saveName() {
    const updated = await apiFetch<WelcomeProfile>("/api/users/me/profile", {
      method: "PATCH",
      body: JSON.stringify({ name }),
    })
    setName(updated.name ?? "")
    void refreshCurrentUser()
    showFlash("Your name has been saved.", "success")
  }

  async function saveCompany() {
    const updated = await apiFetch<{ name: string | null }>("/api/organization", {
      method: "PATCH",
      body: JSON.stringify({ name: company }),
    })
    setCompany(updated.name ?? "")
    void refreshCurrentUser()
    showFlash("Organization name saved.", "success")
  }

  return (
    <div>
      <StickyHeader>
        <div className="flex items-center gap-2 p-2">
          <Tooltip content="Back" placement="bottom">
            <button type="button" onClick={onBack} aria-label="Back" className="btn btn-square">
              <span className="material-symbols-outlined text-lg">arrow_back</span>
            </button>
          </Tooltip>

          <Tooltip content="Archive" placement="bottom">
            <button type="button" onClick={onArchive} aria-label="Archive" className="btn btn-square">
              <span className="material-symbols-outlined text-lg">archive</span>
            </button>
          </Tooltip>

          <div className={MAILBOX_ACTION_CLUSTER_CLASS}>
            <Tooltip content={read ? "Mark unread" : "Mark read"} placement="bottom">
              <button
                type="button"
                onClick={onToggleRead}
                aria-label={read ? "Mark unread" : "Mark read"}
                className={MAILBOX_ACTION_SEGMENT_CLASS}
              >
                <span className="material-symbols-outlined text-lg">{read ? "mark_email_unread" : "drafts"}</span>
              </button>
            </Tooltip>
            <span className={MAILBOX_ACTION_DIVIDER_CLASS} />
            <SnoozeDropdown
              isOpen={snoozeOpen}
              onOpenChange={setSnoozeOpen}
              onSnooze={async () => onSnooze()}
              timezone={user?.time_zone ?? null}
              buttonClassName={MAILBOX_ACTION_SEGMENT_CLASS}
              withHotkey={false}
            />
          </div>
        </div>
      </StickyHeader>

      <div className="mx-auto max-w-2xl px-4 py-8">
        <h1 className="font-accent text-2xl text-base-content text-balance">Introduce yourself</h1>
        <p className="mt-2 text-sm text-base-content/60 text-pretty">
          Your name and photo are visible to your whole team
          {canNameOrganization ? ", and you can set the organization name" : ""}.
        </p>

        {profile === null ? (
          <div className="mt-6 flex justify-center py-10">
            <span className="loading loading-spinner text-base-500" />
          </div>
        ) : (
          <div className="mt-6 overflow-hidden rounded-2xl border border-base-300 divide-y divide-base-300">
            {/* Company first for admins: OAuth autofills name and photo, but the company name
                starts blank, so lead with the field that actually needs them. */}
            {canNameOrganization && (
              <SettingsSection title="Organization" description="Your organization's name, shown across the app.">
                <SaveForm onSave={saveCompany} errorMessage="Could not save the name. Please try again.">
                  <div className="fieldset">
                    <label className="label" htmlFor="welcome_organization">
                      <span className="label-text">Organization name</span>
                    </label>
                    <input
                      className="input input-sm w-full bg-base-200 placeholder-base-500"
                      id="welcome_organization"
                      name="organization"
                      type="text"
                      required
                      placeholder="Organization name"
                      value={company}
                      onChange={e => setCompany(e.target.value)}
                    />
                  </div>
                </SaveForm>
              </SettingsSection>
            )}

            <SettingsSection title="Your profile" description="Your picture and name, as your team sees you.">
              <div className="flex items-start gap-5">
                <AvatarUploader
                  picture={profile.picture}
                  hasCustomAvatar={profile.has_custom_avatar}
                  displayName={name || "Your avatar"}
                  onUpdated={u => setProfile(prev => (prev ? { ...prev, ...u } : prev))}
                />
                <div className="flex-1">
                  <SaveForm onSave={saveName} errorMessage="Could not save your name. Please try again.">
                    <div className="fieldset">
                      <label className="label" htmlFor="welcome_name">
                        <span className="label-text">Name</span>
                      </label>
                      <input
                        className="input input-sm w-full bg-base-200 placeholder-base-500"
                        id="welcome_name"
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
          </div>
        )}

        <p className="mt-6 text-center text-xs text-base-content/50">
          You can change these anytime in{" "}
          {/* /profile/edit is still server-rendered, so this stays a full-document load
              until that page migrates. */}
          <a href="/profile/edit" className="font-medium text-info-content hover:underline">
            Settings
          </a>
          {isAdmin && (
            <>
              {" "}
              or{" "}
              <Link to="/organization/edit" className="font-medium text-info-content hover:underline">
                Organization Settings
              </Link>
            </>
          )}
          .
        </p>

        <div className="mt-6 flex justify-center">
          <button type="button" onClick={onBack} className="btn btn-ghost gap-1.5 text-base-600">
            Skip for now
            <span className="material-symbols-outlined text-base">arrow_forward</span>
          </button>
        </div>
      </div>
    </div>
  )
}
