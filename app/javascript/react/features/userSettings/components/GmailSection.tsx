import { useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { apiFetch } from "~/react/shared/apiFetch"
import { ErrorState } from "~/react/ui/ErrorState"
import { GmailLogo } from "~/react/ui/GmailLogo"
import { LoadingState } from "~/react/ui/LoadingState"
import { showFlash } from "~/shared/flash"

import { useConnectionStatus } from "../hooks/useConnectionStatus"
import type { GmailConnection } from "../types"

const DESCRIPTION = "Connect your Gmail for collaborative email."

export function GmailSection() {
  const { data, setData, loading, error } = useConnectionStatus<GmailConnection>("/api/integrations/gmail/connection")
  const [disconnecting, setDisconnecting] = useState(false)
  const status = data?.status ?? null

  async function disconnect() {
    const confirmed = await confirm({ message: "Are you sure you want to disconnect your Gmail?" })
    if (!confirmed) return
    setDisconnecting(true)
    try {
      await apiFetch("/api/integrations/gmail/connection", { method: "DELETE" })
      // Disconnecting strips the Gmail scope but the Google login remains, so the
      // user can self-serve a reconnect → "disconnected", not "unavailable". It also
      // clears the GMAIL integration, so there's no reconnect nag → requires_reauth false.
      setData({ status: "disconnected", requires_reauth: false })
      showFlash("Gmail has been disconnected.", "success")
    } catch {
      showFlash("Could not disconnect Gmail. Please try again.", "error")
    } finally {
      setDisconnecting(false)
    }
  }

  function body() {
    if (loading) return <LoadingState className="py-6" />
    if (error || status === null) return <ErrorState message="Could not load your Gmail connection." />
    if (status === "connected") {
      return (
        <>
          <p className="text-sm">Your Gmail is connected for collaborative email.</p>
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
          {/* OAuth redirect needs a full-document navigation, not an XHR/SPA swap. */}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => window.location.assign("/integrations/gmail/auth")}
          >
            <span className="w-5">
              <GmailLogo />
            </span>
            Connect Gmail
          </button>
        </div>
      )
    }
    return <p className="text-sm opacity-75">Sign in with Google to connect your Gmail for collaborative email.</p>
  }

  return (
    <SettingsSection title="Gmail" description={DESCRIPTION}>
      {body()}
    </SettingsSection>
  )
}
