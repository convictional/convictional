import { useQuery } from "@tanstack/react-query"

import { OrganizationUpdatesConfiguration } from "~/react/composites/organizationUpdatesConfiguration/OrganizationUpdatesConfiguration"
import { SettingsGroup } from "~/react/composites/settings/SettingsGroup"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { StickyHeader } from "~/react/ui/StickyHeader"

import { BasicsSection } from "./components/BasicsSection"
import { SystemPromptSection } from "./components/SystemPromptSection"
import { organizationQueryOptions } from "./queries"

// Basics and System Prompt both read GET /api/organization, so it's fetched once
// here and passed down; Updates owns its own fetch. Superuser comes from the
// current user (the page is admin-gated by the route's beforeLoad), not from
// server-injected props.
export function OrganizationSettings() {
  const { user } = useCurrentUser()
  const { data: organization, isPending, isError } = useQuery(organizationQueryOptions)

  const isSuperuser = user?.is_superuser ?? false

  function renderBody() {
    if (isPending) return <LoadingState />
    if (isError || !organization) return <ErrorState message="Could not load organization settings." />
    return (
      <SettingsGroup>
        <BasicsSection initialName={organization.name} />
        <OrganizationUpdatesConfiguration />
        {isSuperuser && <SystemPromptSection initialContent={organization.system_prompt ?? ""} />}
      </SettingsGroup>
    )
  }

  return (
    <div>
      <StickyHeader>
        <div className="flex items-center gap-2 p-2">
          <h1 className="text-lg font-accent px-1">Organization Settings</h1>
        </div>
      </StickyHeader>
      <div className="px-2">{renderBody()}</div>
    </div>
  )
}
