import { useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { apiFetch } from "~/react/shared/apiFetch"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { SlackLogo } from "~/react/ui/SlackLogo"
import { showFlash } from "~/shared/flash"

import { useConnectionStatus } from "../hooks/useConnectionStatus"
import type { SlackConnection } from "../types"

const DESCRIPTION = "Connect Slack to bring conversations and notifications into your workspace."

export function SlackSection({ slackAppInstallUrl }: { slackAppInstallUrl: string }) {
  const { data, setData, loading, error } = useConnectionStatus<SlackConnection>("/api/integrations/slack/connection")
  const [disconnecting, setDisconnecting] = useState(false)
  const status = data?.status ?? null

  async function disconnect() {
    const confirmed = await confirm({ message: "Are you sure you want to disconnect Slack?" })
    if (!confirmed) return
    setDisconnecting(true)
    try {
      await apiFetch("/api/integrations/slack/connection", { method: "DELETE" })
      // The org app is still installed, so this user can self-serve a reconnect.
      setData({ status: "disconnected" })
      showFlash("Slack has been disconnected.", "success")
    } catch {
      showFlash("Could not disconnect Slack. Please try again.", "error")
    } finally {
      setDisconnecting(false)
    }
  }

  function body() {
    if (loading) return <LoadingState className="py-6" />
    if (error || status === null) return <ErrorState message="Could not load your Slack connection." />
    if (status === "connected") {
      return (
        <>
          <p className="text-sm">Slack is connected.</p>
          <div className="flex justify-end">
            <button
              type="button"
              className="btn bg-base-200 border border-neutral"
              disabled={disconnecting}
              onClick={disconnect}
            >
              Disconnect
            </button>
          </div>
        </>
      )
    }
    if (status === "disconnected") {
      return (
        <div className="flex justify-end">
          {/* Full-document navigation, not an <a> — see GmailSection for why. */}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => window.location.assign("/integrations/slack/connect")}
          >
            <span className="flex w-5 items-center justify-center">
              <SlackLogo />
            </span>
            Connect Slack
          </button>
        </div>
      )
    }
    return (
      <p className="text-sm opacity-75">
        Slack isn&apos;t installed for your workspace yet. Ask a workspace admin to{" "}
        <a href={slackAppInstallUrl} target="_blank" rel="noopener noreferrer" className="link">
          install Convictional on Slack
        </a>
        , then connect here.
      </p>
    )
  }

  return (
    <SettingsSection title="Slack" description={DESCRIPTION}>
      {body()}
    </SettingsSection>
  )
}
