import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"

import { useConnectionStatus } from "../hooks/useConnectionStatus"
import type { NotionConnection } from "../types"

const DESCRIPTION = "Sync pages from your Notion workspace into Convictional."

// Status-only: connecting Notion needs an internal-integration-token paste, which
// the dedicated /integrations/notion/settings island owns, so this section just
// reports the status and links there. Navigation is a full-document assign so the
// destination island bootstraps fresh.
export function NotionSection() {
  const { data, loading, error } = useConnectionStatus<NotionConnection>("/api/integrations/notion/connection")

  function statusLine() {
    if (loading) return <LoadingState className="py-6" />
    if (error || data === null) return <ErrorState message="Could not load your Notion connection." />
    return data.is_connected ? (
      <p className="text-sm">Notion is connected.</p>
    ) : (
      <p className="text-sm opacity-75">Not connected.</p>
    )
  }

  return (
    <SettingsSection title="Notion" description={DESCRIPTION}>
      {statusLine()}
      <div className="flex justify-end">
        <button
          type="button"
          className="btn bg-base-200 border border-neutral"
          onClick={() => window.location.assign("/integrations/notion/settings")}
        >
          Manage Notion
        </button>
      </div>
    </SettingsSection>
  )
}
