// Eager import: themeApplicator runs at module load and sets <html data-theme>
// before React paints. First import for the same FOUC reason as main.ts.
import "./shared/themeApplicator"
import "./shared/pullToRefresh"

import { QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { applyNativeShellBodyClass } from "./nativeShell"
import { router } from "./react/app/router"
import { queryClient } from "./react/shared/queryClient"
import { IslandErrorBoundary } from "./react/ui/IslandErrorBoundary"
import { initSentry } from "./sentry"

// The SPA entry is deliberately separate from main.ts: it boots only the
// TanStack Router shell and never pulls in Alpine, htmx, channels, or the island
// mounts. The server serves this entry (via layouts/spa.html.jinja) for
// client-routed paths only; every other page keeps the legacy main.ts boot.

// Parity with main.ts: apply before paint so CSS that hides PWA-only chrome in
// the native shell doesn't flash.
applyNativeShellBodyClass()

// No-ops when the server injected no DSN. AppShell also calls setUser once React
// has the authenticated identity; this early call covers errors thrown before then.
initSentry({ user: window.SENTRY_USER ?? null })

// IslandErrorBoundary is the app's shared crash fallback (renders a recovery UI
// and reports to Sentry); mountIsland wraps every island in it, so the SPA root
// gets the same guarantee rather than a blank #root on a render crash.
const rootElement = document.getElementById("root")
if (rootElement) {
  createRoot(rootElement).render(
    <StrictMode>
      <IslandErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </IslandErrorBoundary>
    </StrictMode>
  )
}
