// Eager import: themeApplicator runs at module load and sets <html data-theme>
// before Alpine boots. Importing it first eliminates a small FOUC where the
// page would briefly render in the default theme.
import "./shared/themeApplicator"
import "./shared/pullToRefresh"

import "htmx-ext-alpine-morph"
import "htmx-ext-head-support"
import "htmx-ext-json-enc"
import "htmx-ext-loading-states"
import "htmx-ext-preload"
import "htmx-ext-sse"

import anchor from "@alpinejs/anchor"
import focus from "@alpinejs/focus"
import morph from "@alpinejs/morph"
import sort from "@alpinejs/sort"
import Tooltip from "@ryangjchandler/alpine-tooltip"
import Alpine from "alpinejs"
import htmx from "htmx.org"

import { ChannelsClient, setChannelsClient } from "./channels/client"
import { logConnectionFailureToSentry } from "./channels/logging"
import { createChannelsStore } from "./channels/store"
import { assetVersionReloader } from "./layouts/assetVersionReloader"
import { createThemeStore } from "./layouts/theme"
import {
  applyNativeShellBodyClass,
  isNativeShell,
  notifyNativeAppReady,
  notifyNativeAuthenticated,
} from "./nativeShell"
import { pwaInstallPrompt } from "./pwaInstall/component"
import { registerServiceWorker } from "./pwaInstall/registerServiceWorker"
import { reloadOnOffline } from "./pwaInstall/reloadOnOffline"
import { unmountAll } from "./react/shared/mountIsland"
import { initSentry } from "./sentry"
import { installBfcacheGuard } from "./shared/bfcacheGuard"
import { getCSRFToken, isCSRFFailure, showSessionChangedFlash, initSessionBroadcast } from "./shared/csrf"
import { initializeHotkeys, uninstallHotkeys } from "./shared/hotkeys"
import { sheet } from "./shared/sheet"
import { userSearchFilterComponent } from "./shared/userPicker"

// React islands — each mount module handles element detection and htmx:load re-mounting
import "./react/features/backgroundJobs/mount"
import "./react/features/chatPanel/mount"
import "./react/features/commandPalette/mount"
import "./react/composites/confirmationDialog/htmxBridge"
import "./react/composites/confirmationDialog/mount"
import "./react/composites/organizationUpdatesConfiguration/mount"
import "./react/composites/toaster/mount"
import "./react/composites/workspaceCollaborators/mount"
import "./react/features/feedback/mount"
import "./react/features/goalAlignmentsIndex/mount"
import "./react/features/goalAlignmentsShow/mount"
import "./react/features/groupsIndex/mount"
import "./react/features/mainNav/mount"
import "./react/features/meetingShow/mount"
import "./react/features/meetingsCollectionsIndex/mount"
import "./react/features/meetingsIndex/mount"
import "./react/features/meetingsUpcomingIndex/mount"
import "./react/features/notion/mount"
import "./react/features/organizationUsers/mount"
import "./react/features/research/dialog/mount"
import "./react/features/research/scheduled/mount"
import "./react/features/searchResults/mount"
import "./react/features/userSettings/mount"
import "./react/features/workspaceAccessRequest/mount"

// Apply before paint so CSS that hides PWA-only chrome in the native shell
// doesn't flash. Component-level suppression (install banner, push prompt)
// is gated on isNativeShell() in the components that own them.
applyNativeShellBodyClass()

// Initialize Sentry as early as possible so pageload tracing and any early
// errors are captured. No-ops when the server injected no DSN (e.g. local dev).
// SENTRY_USER is set by the authenticated layout (application.html.jinja).
initSentry({ headModuleScriptCanary: true, user: window.SENTRY_USER ?? null })

// Prevent double initialization
if (window.Alpine) {
  console.warn("The bundle is already loaded. This often coincides with releases.")
  window.location.reload()
}

// Expose global objects
window.htmx = htmx
window.Alpine = Alpine

// Register a document-level boot listener at most once per window. If this
// module graph is ever evaluated twice in the same realm, a second run must
// not add a second copy of these listeners: duplicates are never removed and
// would pin the whole module graph on the persistent top document.
declare global {
  interface Window {
    __convictionalBootListeners?: Set<string>
  }
}
const boundBootListeners: Set<string> = (window.__convictionalBootListeners ??= new Set())
function addBootListener(type: string, handler: EventListener): void {
  if (boundBootListeners.has(type)) return
  boundBootListeners.add(type)
  document.addEventListener(type, handler)
}

// Initialize channels only on authenticated pages
const isAuthenticated = document.body.dataset.authenticated === "true"
const channelsClient = isAuthenticated ? new ChannelsClient() : null
if (channelsClient) {
  setChannelsClient(channelsClient)
  channelsClient.connect().catch(error => {
    console.error("Failed to initialize channels client:", error)

    // Log to Sentry for production monitoring
    logConnectionFailureToSentry("WebSocket channels initial connection failed", {
      attemptCount: 0,
      fallbackMode: false, // Don't know yet, connection hasn't started
    })
  })
} else {
  console.log("[Channels] Skipping initialization on unauthenticated page")
}

// Set timezone cookie for backend
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
document.cookie = `timezone=${timezone};path=/`

// Configure HTMX to include CSRF tokens
addBootListener("htmx:configRequest", event => {
  const detail = (event as CustomEvent).detail
  detail.headers["X-CSRFToken"] = getCSRFToken() || ""
})

// Broadcast session identity across tabs so other tabs detect login/logout
initSessionBroadcast()

// Guard against the bfcache restoring an authenticated page after logout.
installBfcacheGuard()

// Show a persistent alert when a CSRF token mismatch is detected
addBootListener("htmx:responseError", event => {
  const xhr = (event as CustomEvent).detail.xhr
  if (isCSRFFailure(xhr.status, !!xhr.getResponseHeader("X-CSRF-Failure"))) {
    showSessionChangedFlash()
  }
})

reloadOnOffline()

// Register Alpine stores
Alpine.store("theme", createThemeStore())
if (channelsClient) {
  Alpine.store("channels", createChannelsStore(channelsClient))
}

// Register Alpine components
Alpine.data("sheet", sheet)
Alpine.data("userSearchFilter", userSearchFilterComponent)
Alpine.data("assetVersionReloader", assetVersionReloader)
Alpine.data("pwaInstallPrompt", pwaInstallPrompt)

// Register Alpine plugins and start
Alpine.plugin(anchor)
Alpine.plugin(focus)
Alpine.plugin(sort)
Alpine.plugin(morph)
Alpine.plugin(Tooltip)
Alpine.start()

// Initialize hotkeys on page load
addBootListener("DOMContentLoaded", () => {
  initializeHotkeys()
  // Tell the native shell the WebView is interactive so it can dismiss the
  // splash. No-op outside the native shell.
  notifyNativeAppReady()
  if (isAuthenticated) {
    notifyNativeAuthenticated()
  }
})

// The PWA service worker handles web push for desktop browsers; the native
// shell uses APNs via expo-notifications instead and doesn't need the SW for
// push at all. Skipping registration here avoids spurious permission prompts
// and double subscriptions when both web push and native push could fire.
if (!isNativeShell()) {
  registerServiceWorker()
}

// Uninstall hotkeys before HTMX swaps content (especially important for boosted navigation)
addBootListener("htmx:beforeSwap", event => {
  const target = (event as CustomEvent).detail?.target
  if (target) {
    uninstallHotkeys(target)
  }
})

// Initialize when HTMX loads new content (boosted pages, fragments, etc.)
addBootListener("htmx:load", event => {
  const target = (event as CustomEvent).detail?.elt
  if (target) {
    initializeHotkeys(target)
  }
})

// Tear down React island roots when the document is actually discarded so an
// abandoned root can't dangle. Skip bfcache suspends (persisted), which may be
// restored and would otherwise come back with blanked islands.
addBootListener("pagehide", event => {
  if (!(event as PageTransitionEvent).persisted) unmountAll()
})
