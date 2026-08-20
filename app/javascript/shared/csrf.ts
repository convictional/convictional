import * as Sentry from "@sentry/browser"

import { showFlash } from "./flash"

const SESSION_CHANNEL_NAME = "convictional-session"
const SESSION_CHANGED_MESSAGE = "Your session has changed — click to reload"

let lastKnownToken: string | null = null
let sessionChangedShown = false

function showSessionChangedFlash(): void {
  if (sessionChangedShown) return
  sessionChangedShown = true
  showFlash(SESSION_CHANGED_MESSAGE, "error", window.location.href, true)
}

function readCSRFMeta(): { token: string; sessionCreatedAt: string } | null {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')
  if (!meta) return null
  return { token: meta.content, sessionCreatedAt: meta.dataset.sessionCreatedAt ?? "" }
}

function getCSRFToken(): string | null {
  const token = readCSRFMeta()?.token || null
  if (token) {
    lastKnownToken = token
  }
  const result = token || lastKnownToken
  if (!result) {
    Sentry.captureMessage("CSRF token is null", "warning")
  }
  return result
}

function isCSRFFailure(status: number, hasHeader: boolean): boolean {
  return status === 403 && hasHeader
}

async function fetchWithCSRF(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getCSRFToken()
  if (token) {
    options.headers = {
      ...options.headers,
      "X-CSRFToken": token,
    }
  }

  const response = await fetch(url, options)

  if (isCSRFFailure(response.status, response.headers.has("X-CSRF-Failure"))) {
    showSessionChangedFlash()
  }

  return response
}

function initSessionBroadcast(): void {
  if (typeof BroadcastChannel === "undefined") return

  const meta = readCSRFMeta()
  const sessionCreatedAt = meta?.sessionCreatedAt ?? ""
  lastKnownToken = meta?.token || null

  const channel = new BroadcastChannel(SESSION_CHANNEL_NAME)

  channel.onmessage = (event: MessageEvent<string>) => {
    const remoteCreatedAt = event.data
    if (remoteCreatedAt === sessionCreatedAt) return

    const isAuthenticated = document.body.dataset.authenticated === "true"
    if (!isAuthenticated) return

    lastKnownToken = null
    showSessionChangedFlash()
  }

  channel.postMessage(sessionCreatedAt)
}

function resetSessionChangedFlag(): void {
  sessionChangedShown = false
}

export {
  getCSRFToken,
  fetchWithCSRF,
  isCSRFFailure,
  initSessionBroadcast,
  showSessionChangedFlash,
  resetSessionChangedFlag,
  SESSION_CHANGED_MESSAGE,
}
