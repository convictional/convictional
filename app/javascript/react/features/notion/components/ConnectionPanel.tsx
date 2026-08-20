import { type FormEvent, useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import type { NotionConnectionResult } from "~/react/features/notion/types"
import { ApiError } from "~/react/shared/apiFetch"
import { EmptyState } from "~/react/ui/EmptyState"
import { SubmitButton } from "~/react/ui/SubmitButton"

interface ConnectionPanelProps {
  isConnected: boolean
  workspaceName: string | null
  onConnect: (accessToken: string) => Promise<NotionConnectionResult>
  onDisconnect: () => Promise<void>
}

const TOKEN_REJECTED_FALLBACK = "Couldn't connect to Notion. Please check the token and try again."

function connectErrorMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 422 || error.status === 502)) {
    const detail = error.body?.detail
    if (typeof detail === "string") return detail
  }
  return TOKEN_REJECTED_FALLBACK
}

export function ConnectionPanel({ isConnected, workspaceName, onConnect, onDisconnect }: ConnectionPanelProps) {
  return isConnected ? (
    <ConnectedView workspaceName={workspaceName} onDisconnect={onDisconnect} />
  ) : (
    <DisconnectedView onConnect={onConnect} />
  )
}

function DisconnectedView({ onConnect }: { onConnect: ConnectionPanelProps["onConnect"] }) {
  const [token, setToken] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!token.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await onConnect(token.trim())
    } catch (e) {
      setError(connectErrorMessage(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <EmptyState title="Notion not connected">
      <div className="flex flex-col gap-3 text-left">
        <p className="text-sm opacity-50 text-pretty">
          Create a Notion internal integration, share the pages you want with it, then paste the integration token
          below.{" "}
          <a
            href="https://developers.notion.com/docs/create-a-notion-integration"
            target="_blank"
            rel="noopener noreferrer"
            className="link"
          >
            How to create a Notion integration
          </a>
          .
        </p>
        <form onSubmit={handleSubmit}>
          <div className="fieldset">
            <label className="text-xs opacity-60 mb-1 block" htmlFor="notion_access_token">
              Notion integration token
            </label>
            <input
              id="notion_access_token"
              type="password"
              name="access_token"
              className="input input-bordered w-full"
              placeholder="secret_..."
              autoComplete="off"
              value={token}
              onChange={e => setToken(e.target.value)}
              required
            />
          </div>
          {error && <p className="text-sm text-error mt-2">{error}</p>}
          <div className="flex justify-end mt-3">
            <SubmitButton submitting={submitting}>Connect Notion</SubmitButton>
          </div>
        </form>
      </div>
    </EmptyState>
  )
}

function ConnectedView({
  workspaceName,
  onDisconnect,
}: {
  workspaceName: string | null
  onDisconnect: ConnectionPanelProps["onDisconnect"]
}) {
  const [disconnecting, setDisconnecting] = useState(false)

  async function handleDisconnect() {
    const confirmed = await confirm({
      message: "Are you sure you want to disconnect Notion? Synced pages will be removed.",
    })
    if (!confirmed) return
    setDisconnecting(true)
    try {
      await onDisconnect()
    } finally {
      setDisconnecting(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm">
        Connected to <span className="font-semibold">{workspaceName || "your Notion workspace"}</span>.
      </p>
      <div className="flex justify-end">
        <button
          type="button"
          className={`btn bg-base-200 border border-neutral${disconnecting ? " loading loading-sm loading-spinner" : ""}`}
          disabled={disconnecting}
          onClick={handleDisconnect}
        >
          Disconnect
        </button>
      </div>
    </div>
  )
}
