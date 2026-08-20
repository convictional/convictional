import { useEffect, useState } from "react"

import { SettingsGroup } from "~/react/composites/settings/SettingsGroup"
import { apiFetch } from "~/react/shared/apiFetch"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { StickyHeader } from "~/react/ui/StickyHeader"

import { BioSection } from "./components/BioSection"
import { CalendarSection } from "./components/CalendarSection"
import { GmailSection } from "./components/GmailSection"
import { NotionSection } from "./components/NotionSection"
import { ProfileSection } from "./components/ProfileSection"
import { SlackSection } from "./components/SlackSection"
import { TimezoneSection } from "./components/TimezoneSection"
import type { Profile, UserSettingsProps } from "./types"

// The whole My Settings page as a single island. The profile resource is fetched
// once here and fed to the sections that edit it (Profile, Timezone, Bio); each
// integration section owns its own status fetch + mutations, mirroring the
// organizationSettings island. Sections render in the original page order.
export function UserSettings({ hasGoogleOauth, slackAppInstallUrl }: UserSettingsProps) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    apiFetch<Profile>("/api/users/me/profile")
      .then(data => {
        if (cancelled) return
        setProfile(data)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) return <LoadingState />
  if (!profile) return <ErrorState message="Could not load your settings." />

  return (
    <div>
      <StickyHeader>
        <div className="flex items-center gap-2 p-2">
          <h1 className="text-lg font-accent px-1">My Settings</h1>
        </div>
      </StickyHeader>
      <div className="px-2 space-y-8">
        <SettingsGroup title="Account">
          <ProfileSection profile={profile} />
          <TimezoneSection initialTimeZone={profile.time_zone} />
          <BioSection initialBio={profile.bio} />
        </SettingsGroup>
        <SettingsGroup title="Integrations">
          {hasGoogleOauth && <GmailSection />}
          <CalendarSection />
          <SlackSection slackAppInstallUrl={slackAppInstallUrl} />
          <NotionSection />
        </SettingsGroup>
      </div>
    </div>
  )
}
