import * as Sentry from "@sentry/browser"
import { Outlet, useMatches } from "@tanstack/react-router"
import { useEffect } from "react"

import { notifyNativeSetUser } from "~/nativeShell"
import { ConfirmationDialog } from "~/react/composites/confirmationDialog/ConfirmationDialog"
import { GmailReauthBadge } from "~/react/composites/GmailReauthBadge"
import { Toaster } from "~/react/composites/toaster/Toaster"
import { ChatPanel } from "~/react/features/chatPanel/ChatPanel"
import { CommandPalette } from "~/react/features/commandPalette/CommandPalette"
import { FeedbackDialog } from "~/react/features/feedback/FeedbackDialog"
import { MainNav } from "~/react/features/mainNav/MainNav"
import { ResearchDialog } from "~/react/features/research/dialog/ResearchDialog"
import { useAssetVersionReloader } from "~/react/shared/hooks/useAssetVersionReloader"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { consumeFlashes } from "~/react/shared/stores/currentUser"
import { toastStore } from "~/react/shared/stores/toast"
import { FLOATING_PORTAL_ROOT_ID } from "~/react/ui/floatingPortalRoot"
import { consumeQueuedFlashes } from "~/shared/flash"

import { resolveClipContainerOverflowX, resolveHideMobileNav, resolveShowGmailReauthBadge } from "./shellRouteFlags"
import { resolveShellWidth, shellWidthClassName } from "./shellWidth"

// FlashLevel (success/error/warning/info) collapses onto the toaster's two
// levels; anything not clearly positive surfaces as an error.
function toastLevel(flashLevel: string): "error" | "success" {
  return flashLevel === "success" || flashLevel === "info" ? "success" : "error"
}

// The authenticated chrome as a router layout route. It re-parents the existing
// chrome islands as plain children; their mount.tsx modules keep serving legacy
// Jinja pages in parallel. The bootstrap payload, channels client, and toast
// bridge are all wired in the route's beforeLoad (shellBootstrap) before this
// subtree renders, so currentUser is populated by first paint.
export function AppShell() {
  const { user } = useCurrentUser()
  const isMobile = useIsMobile()
  const matches = useMatches()

  useAssetVersionReloader()

  // Clear Sentry's user when the session resets (user → null), not only set it,
  // so a stale identity can't follow anonymous activity in the same tab. In the
  // native shell, forward the same identity across the bridge so the native
  // Sentry SDK attributes native-shell errors to the tester too.
  useEffect(() => {
    const identity = user ? { id: user.id, email: user.email } : null
    Sentry.setUser(identity)
    notifyNativeSetUser(identity)
  }, [user])

  // Drain server flashes from the bootstrap payload into the toaster, once.
  useEffect(() => {
    for (const flash of consumeFlashes()) {
      toastStore.getState().show({ message: flash.content, level: toastLevel(flash.level), persistent: false })
    }
    // Also drain client flashes queued before a full-page navigation (e.g. the
    // show-page snooze confirmation, which can't survive the redirect in-page).
    for (const flash of consumeQueuedFlashes()) {
      toastStore.getState().show({ message: flash.message, level: toastLevel(flash.level), persistent: false })
    }
  }, [])

  // beforeLoad guarantees the user is loaded before the shell renders; null is
  // only the brief pre-hydration gap, so render the chrome scaffold without it.
  const width = resolveShellWidth(matches)
  const clipOverflowX = resolveClipContainerOverflowX(matches)
  // On mobile, a route can go full-screen by suppressing the top nav (and its
  // bottom offset below). Desktop always keeps the nav. The `data-mobile-nav`
  // attribute on #container below publishes this so main.css can zero the
  // --mobile-nav-* vars for the whole subtree.
  const hideMobileNav = isMobile && resolveHideMobileNav(matches)
  const showGmailReauthBadge = resolveShowGmailReauthBadge(matches)

  return (
    <>
      {!hideMobileNav && (
        <div className="px-2 relative z-40 bg-base-100" data-nav-sticky-wrapper>
          <div className="w-full max-w-4xl mx-auto py-2">
            {user && (
              <MainNav
                isAdmin={user.is_admin}
                isSuperuser={user.is_superuser}
                organizationName={user.organization_name}
              />
            )}
          </div>
        </div>
      )}

      <CommandPalette />
      <ResearchDialog />
      {/* Always-mounted portal root so tooltips/floating elements survive client nav. */}
      <div id={FLOATING_PORTAL_ROOT_ID} />

      {/* Below the nav, above the content — the legacy application-layout position.
          Route-gated here (staticData.showGmailReauthBadge); the badge itself no-ops
          unless the Gmail connection actually needs reauth. */}
      {showGmailReauthBadge && <GmailReauthBadge />}

      {/* overflow-x-clip is opt-in per route (clipContainerOverflowX): the
          document editor's comment cards/gutter are positioned beyond the content
          column and would otherwise induce horizontal page scroll, but other
          routes keep their natural overflow. `clip` (not `hidden`) preserves the
          sticky editor header. */}
      <main
        id="container"
        // `data-mobile-nav="hidden"` on #container is the contract main.css reads
        // to zero --mobile-nav-* for the subtree, so descendants that position off
        // --mobile-nav-offset (e.g. the chat composer) collapse to the bottom when
        // the nav is hidden. The bottom padding can then be unconditional on
        // mobile — the var carries the offset (0 when hidden).
        data-mobile-nav={hideMobileNav ? "hidden" : "visible"}
        className={`${isMobile ? "px-2 pb-[var(--mobile-nav-offset)]" : "px-2"}${clipOverflowX ? " overflow-x-clip" : ""}`}
      >
        <div className={shellWidthClassName(width)}>
          <Outlet />
        </div>
      </main>

      {!isMobile && <ChatPanel />}
      <FeedbackDialog uploadUrl={user?.feedback_upload_url ?? ""} />
      <ConfirmationDialog />
      <Toaster />
    </>
  )
}
