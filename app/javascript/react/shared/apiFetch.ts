// Reuses the HTMX CSRF/session infrastructure so React islands and HTMX pages
// share the same auth behavior (token rotation, session-changed flash, etc.).
import * as Sentry from "@sentry/browser"

import { withRedirectTo } from "~/react/shared/returnTo"
import { getCSRFToken, isCSRFFailure, showSessionChangedFlash } from "~/shared/csrf"

export class ApiError extends Error {
  status: number
  body: Record<string, unknown> | null

  constructor(status: number, body: Record<string, unknown> | null) {
    super(`Request failed with status ${status}`)
    this.name = "ApiError"
    this.status = status
    this.body = body
  }
}

// ApiError messages are generic ("Request failed with status N") and FastAPI
// detail strings aren't user-facing, so we default to the caller-provided
// fallback for all errors.
export function errorMessage(_error: unknown, fallback: string): string {
  return fallback
}

// A 403 from any resource API carries the request-access URL as data (see the
// backend request_access_handler): a same-org non-collaborator gets 403 +
// request_access_url. Pull it out so a view can offer to request access rather
// than dead-ending on an error. The contract is resource-neutral — documents,
// email threads, and any future collaboratable resource share it.
export function accessDeniedUrl(error: unknown): string | undefined {
  if (!(error instanceof ApiError) || error.status !== 403) return undefined
  const url = error.body?.request_access_url
  return typeof url === "string" ? url : undefined
}

// Statuses the caller treats as control flow rather than failures (e.g. a 404
// for an optional sub-resource that may legitimately be absent). They still
// throw an ApiError so the caller can branch, but are not reported to Sentry.
interface ApiFetchOptions {
  expectedStatuses?: number[]
}

const UUID_SEGMENT = /\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi
const NUMERIC_SEGMENT = /\/\d+/g

// Collapse resource identifiers so requests to the same endpoint share a
// fingerprint regardless of which record they targeted.
function normalizeEndpoint(url: string): string {
  return url.split("?")[0].replace(UUID_SEGMENT, "/:id").replace(NUMERIC_SEGMENT, "/:id")
}

let navigationAbortController: AbortController | null = null
let pagehideListenerInstalled = false

// A hard browser navigation aborts in-flight fetches with `TypeError: Failed to
// fetch`. If the awaited rejection's reaction microtask isn't processed before
// the realm tears down, it strands and pins the entire prior JS realm (~20 MB
// per navigation), eventually OOMing the renderer. Aborting on `pagehide` — which
// fires while the realm is still alive and pumping microtasks — forces the
// rejection to be handled so the realm can be freed. The single listener is a
// per-page-lifetime module singleton and intentionally never removed.
function navigationAbortSignal(): AbortSignal {
  if (navigationAbortController === null) {
    navigationAbortController = new AbortController()
  }
  if (!pagehideListenerInstalled && typeof window !== "undefined") {
    pagehideListenerInstalled = true
    window.addEventListener("pagehide", () => {
      navigationAbortController?.abort()
      // Swap in a fresh controller so a bfcache restore starts clean.
      navigationAbortController = new AbortController()
    })
  }
  return navigationAbortController.signal
}

export async function apiFetch<T = unknown>(
  url: string,
  options: RequestInit = {},
  { expectedStatuses = [] }: ApiFetchOptions = {}
): Promise<T> {
  const token = getCSRFToken()
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers as Record<string, string>),
  }

  if (token) {
    headers["X-CSRFToken"] = token
  }

  if (options.body && typeof options.body === "string") {
    headers["Content-Type"] = headers["Content-Type"] || "application/json"
  }

  const navSignal = navigationAbortSignal()
  const signal = options.signal ? AbortSignal.any([navSignal, options.signal]) : navSignal

  const response = await fetch(url, { ...options, headers, credentials: "same-origin", signal })

  if (isCSRFFailure(response.status, response.headers.has("X-CSRF-Failure"))) {
    showSessionChangedFlash()
  }

  if (response.status === 401) {
    // Full-document redirect to the server-rendered login page, carrying the
    // current location so the server returns here after auth (the API path is
    // never the redirect target — remember_location() skips /api/). apiFetch is
    // shared with non-router islands, so it can't assume a router; the
    // router-aware counterpart for client routes is redirectToLogin(), which
    // uses the same `redirect_to` contract.
    window.location.href = withRedirectTo("/login")
    throw new ApiError(401, null)
  }

  const body =
    response.status === 204
      ? null
      : response.headers.get("content-type")?.includes("application/json")
        ? await response.json()
        : null

  if (!response.ok) {
    const error = new ApiError(response.status, body)
    // Surface server-side failures to Sentry rather than leaking FastAPI's raw
    // detail strings to users; callers are responsible for showing a friendly
    // fallback message. Statuses the caller declared expected are control flow,
    // not failures, so they skip Sentry.
    if (!expectedStatuses.includes(response.status)) {
      const endpoint = normalizeEndpoint(url)
      Sentry.withScope(scope => {
        // Every ApiError is thrown from this one line, so Sentry's default
        // stack-trace grouping collapses unrelated failures (a 429 rate-limit,
        // a 422 validation error, a 500) across every endpoint into a single
        // issue. Fingerprint by status + endpoint so each is its own issue, and
        // expose both as tags so they're filterable/aggregatable (extras are not).
        scope.setFingerprint(["api-error", String(response.status), endpoint])
        scope.setTags({ "api.status": String(response.status), "api.endpoint": endpoint })
        scope.setExtras({ url, status: response.status, body })
        scope.captureException(error)
      })
    }
    throw error
  }

  return body as T
}
