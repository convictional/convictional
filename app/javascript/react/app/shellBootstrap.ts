import { redirect } from "@tanstack/react-router"

import { ChannelsClient, getChannelsClient, setChannelsClient } from "~/channels/client"
import { logConnectionFailureToSentry } from "~/channels/logging"
import { registerToastEventBridge } from "~/react/composites/toaster/eventBridge"
import { ApiError } from "~/react/shared/apiFetch"
import { redirectToLogin } from "~/react/shared/routerGuards"
import { isAssetVersionStale } from "~/react/shared/stores/assetVersionStore"
import { getCurrentUser, type CurrentUser } from "~/react/shared/stores/currentUser"

// Connect the realtime client once for SPA pages, replacing main.ts's
// `data-authenticated` gate (legacy Jinja pages keep that path). SPA islands
// subscribe via the React useChannel hook, which resolves this same singleton
// through useChannelsClient().
function bootChannels(): void {
  if (getChannelsClient()) return
  const client = new ChannelsClient()
  setChannelsClient(client)
  client.connect().catch(() => {
    logConnectionFailureToSentry("WebSocket channels initial connection failed", {
      attemptCount: 0,
      fallbackMode: false,
    })
  })
}

// beforeLoad work for the AppShell layout route: fetch the bootstrap payload
// (populating the currentUser query cache), apply the server-parity guards, and wire the
// SPA-wide singletons — all before any shell route renders. Extracted from the
// route so the branches are unit testable without standing up a router.
//
// getCurrentUser() is fetch-once, so calling this on every shell navigation is
// a cheap cache read after the first load.
//
// When the asset-version channel has marked the session stale (see
// useAssetVersionReloader), throw a redirect to force a full-document load to
// the destination. Thrown from beforeLoad so TanStack cancels the SPA route
// change and the stale destination's loaders/effects never run.
export async function loadShellBootstrap(destinationHref: string): Promise<CurrentUser> {
  let user: CurrentUser
  try {
    user = await getCurrentUser()
  } catch (error) {
    // apiFetch already kicks off a full-document login redirect on 401; the
    // router-aware redirect is its counterpart for client routes, so a 401
    // lands on /login either way (see routerGuards + apiFetch).
    if (error instanceof ApiError && error.status === 401) {
      redirectToLogin()
    }
    throw error
  }

  // React runs a child's effects before its parent's, so a child island that
  // subscribes to channels or calls showFlash() on mount would reach a null
  // client / unregistered listener if this waited for an AppShell effect.
  // beforeLoad runs before the whole shell subtree renders, so wire them here.
  registerToastEventBridge()
  bootChannels()

  if (isAssetVersionStale()) {
    throw redirect({ href: destinationHref, reloadDocument: true })
  }

  return user
}
